import type {IncomingMessage, ServerResponse} from 'node:http'
import {context, settings, type TaskResponse} from '@devvit/web/server'
import {createThread, type ThreadConfig, updateThread} from './megathread.ts'
import {poll} from './poll.ts'
import {
  acquirePollLock,
  loadState,
  releasePollLock,
  saveState,
} from './state.ts'
import {
  getLatestVodUrl,
  getStream,
  getTopClip,
  type TwitchCredentials,
} from './twitch.ts'

type ErrorRsp = {error: string; status: number}

export async function onReq(
  reqMsg: IncomingMessage,
  rspMsg: ServerResponse,
): Promise<void> {
  try {
    if (
      reqMsg.method === 'POST' &&
      reqMsg.url === '/internal/scheduler/poll-stream'
    ) {
      writeJson<TaskResponse>(200, await routePollStream(), rspMsg)
    } else {
      writeJson<ErrorRsp>(404, {error: 'not found', status: 404}, rspMsg)
    }
  } catch (err) {
    const msg = `server error; ${err instanceof Error ? err.stack : err}`
    console.error(msg)
    writeJson<ErrorRsp>(500, {error: msg, status: 500}, rspMsg)
  }
}

async function routePollStream(): Promise<TaskResponse> {
  const [
    enabled,
    channel,
    gracePeriodMinutes,
    flairText,
    flairCssClass,
    legacyBotUsernames,
    clientId,
    clientSecret,
  ] = await Promise.all([
    settings.get<boolean>('enabled'),
    settings.get<string>('twitchChannel'),
    settings.get<number>('restartGracePeriodMinutes'),
    settings.get<string>('flairText'),
    settings.get<string>('flairCssClass'),
    settings.get<string>('legacyBotUsernames'),
    settings.get<string>('twitchClientId'),
    settings.get<string>('twitchClientSecret'),
  ])

  if (enabled === false) return {}
  if (!clientId || !clientSecret) {
    console.error(
      'Twitch credentials are not set; run `npx devvit settings set twitchClientId` and `twitchClientSecret`',
    )
    return {}
  }

  const twitchChannel = channel || 'Northernlion'
  const creds: TwitchCredentials = {clientId, clientSecret}
  const threadConfig: ThreadConfig = {
    subredditName: context.subredditName,
    flairText: flairText ?? '[MEGA THREAD]',
    flairCssClass: flairCssClass ?? 'mega',
    legacyBotUsernames: (legacyBotUsernames ?? '')
      .split(',')
      .map(name => name.trim().replace(/^u\//i, ''))
      .filter(Boolean),
  }

  if (!(await acquirePollLock())) {
    console.warn('Previous poll still running; skipping this tick')
    return {}
  }
  try {
    await poll({
      channel: twitchChannel,
      restartGracePeriodMs: (gracePeriodMinutes ?? 30) * 60_000,
      now: () => new Date(),
      getStream: () => getStream(creds, twitchChannel),
      getTopClip: (broadcasterId, startedAt) =>
        getTopClip(creds, broadcasterId, startedAt),
      getLatestVodUrl: broadcasterId => getLatestVodUrl(creds, broadcasterId),
      createThread: (title, body) => createThread(threadConfig, title, body),
      updateThread,
      loadState,
      saveState,
    })
  } finally {
    await releasePollLock()
  }
  return {}
}

function writeJson<T>(
  status: number,
  json: Readonly<T>,
  rsp: ServerResponse,
): void {
  const body = JSON.stringify(json)
  const len = Buffer.byteLength(body)
  rsp.writeHead(status, {
    'Content-Length': len,
    'Content-Type': 'application/json',
  })
  rsp.end(body)
}
