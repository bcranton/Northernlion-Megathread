import type {T3} from '@devvit/web/shared'
import {buildThreadBody, buildThreadTitle, type Clip} from './format.ts'
import type {StreamState} from './state.ts'
import type {LiveStream} from './twitch.ts'

/** How long a stream must stay offline before the thread is finalized. */
export const finalizeDelayMs = 2 * 60_000

export type PollDeps = {
  channel: string
  restartGracePeriodMs: number
  now(): Date
  getStream(): Promise<LiveStream | undefined>
  getTopClip(
    broadcasterId: string,
    startedAt: string,
  ): Promise<Clip | undefined>
  getLatestVodUrl(broadcasterId: string): Promise<string | undefined>
  createThread(title: string, body: string): Promise<T3>
  updateThread(threadId: T3, body: string): Promise<void>
  loadState(): Promise<StreamState | undefined>
  saveState(state: Readonly<StreamState>): Promise<void>
}

/**
 * One scheduler tick. Compares Twitch's view of the stream against the saved
 * state and creates, updates or finalizes the thread to match.
 *
 * This replaces the old EventSub handlers: stream.online is "live with no live
 * state", channel.update is "live and the game changed", and stream.offline is
 * "not live but the state says live".
 */
export async function poll(deps: PollDeps): Promise<void> {
  const stream = await deps.getStream()
  const state = await deps.loadState()

  if (stream) await onLive(deps, stream, state)
  else if (state?.isLive) await onOffline(deps, state)
}

async function onLive(
  deps: PollDeps,
  stream: LiveStream,
  state: StreamState | undefined,
): Promise<void> {
  const game = stream.gameName || undefined

  if (state?.isLive) {
    // Back before finalization, or still going: cancel any pending finalize
    // and add the game if it changed.
    const docket = appendGame(state.docket, game)
    if (docket !== state.docket) {
      await deps.updateThread(state.threadId, liveBody(deps, docket))
      console.log(`Updated docket for ${deps.channel}: ${docket.join(', ')}`)
    }
    if (docket !== state.docket || state.offlineSince) {
      if (state.offlineSince) {
        console.log(`Stream ${deps.channel} came back before finalization`)
      }
      await deps.saveState({...state, docket, offlineSince: undefined})
    }
    return
  }

  if (state?.endedAt && isWithinGracePeriod(deps, state.endedAt)) {
    console.log(
      `Reactivating recently-ended thread for ${deps.channel} (ended at ${state.endedAt})`,
    )
    const docket = appendGame(state.docket, game)
    await deps.updateThread(state.threadId, liveBody(deps, docket))
    await deps.saveState({...state, docket, isLive: true, endedAt: undefined})
    return
  }

  console.log(`Stream online: ${deps.channel} (started at ${stream.startedAt})`)
  const docket = game ? [game] : []
  const threadId = await deps.createThread(
    buildThreadTitle(deps.now()),
    liveBody(deps, docket),
  )
  await deps.saveState({
    threadId,
    broadcasterId: stream.broadcasterId,
    docket,
    streamStart: stream.startedAt,
    isLive: true,
  })
}

async function onOffline(deps: PollDeps, state: StreamState): Promise<void> {
  const now = deps.now()

  if (!state.offlineSince) {
    console.log(`Stream offline: ${deps.channel}; waiting for clips and VOD`)
    await deps.saveState({...state, offlineSince: now.toISOString()})
    return
  }

  if (now.getTime() - Date.parse(state.offlineSince) < finalizeDelayMs) return

  // A missing clip or VOD shouldn't block finalization; a failed edit should
  // (it throws and the next tick retries).
  const [clip, vodUrl] = await Promise.all([
    deps
      .getTopClip(state.broadcasterId, state.streamStart)
      .catch(err => void console.error(`Failed to fetch top clip: ${err}`)),
    deps
      .getLatestVodUrl(state.broadcasterId)
      .catch(err => void console.error(`Failed to fetch VOD: ${err}`)),
  ])

  await deps.updateThread(
    state.threadId,
    buildThreadBody({
      channel: deps.channel,
      docket: state.docket,
      clip: clip ?? undefined,
      vodUrl: vodUrl ?? undefined,
      isLive: false,
    }),
  )
  await deps.saveState({
    ...state,
    isLive: false,
    offlineSince: undefined,
    endedAt: now.toISOString(),
  })
  console.log(`Finalized thread for ${deps.channel}`)
}

/** Returns the docket with game appended, or the same array if unchanged. */
function appendGame(docket: string[], game: string | undefined): string[] {
  if (!game || docket.at(-1) === game) return docket
  return [...docket, game]
}

function isWithinGracePeriod(deps: PollDeps, endedAt: string): boolean {
  return deps.now().getTime() - Date.parse(endedAt) < deps.restartGracePeriodMs
}

function liveBody(deps: PollDeps, docket: readonly string[]): string {
  return buildThreadBody({channel: deps.channel, docket, isLive: true})
}
