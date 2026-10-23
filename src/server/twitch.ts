import {redis} from '@devvit/web/server'
import type {Clip} from './format.ts'

const authURL = 'https://id.twitch.tv/oauth2/token'
const apiURL = 'https://api.twitch.tv/helix'
const tokenKey = 'twitch:token'

export type TwitchCredentials = {clientId: string; clientSecret: string}

export type LiveStream = {
  broadcasterId: string
  gameName: string
  startedAt: string
}

/** Fetch or return the cached app access token (Client Credentials flow). */
async function getAppAccessToken(creds: TwitchCredentials): Promise<string> {
  const cached = await redis.get(tokenKey)
  if (cached) return cached

  const rsp = await fetch(authURL, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams({
      client_id: creds.clientId,
      client_secret: creds.clientSecret,
      grant_type: 'client_credentials',
    }),
  })
  if (!rsp.ok) {
    throw Error(
      `Twitch token request failed: ${rsp.status} ${await rsp.text()}`,
    )
  }
  const data = (await rsp.json()) as {access_token: string; expires_in: number}

  // Refresh 60 seconds before actual expiry.
  const expiration = new Date(Date.now() + (data.expires_in - 60) * 1000)
  await redis.set(tokenKey, data.access_token, {expiration})
  console.log(
    `Obtained Twitch app access token (expires in ${data.expires_in}s)`,
  )
  return data.access_token
}

/**
 * GET a Helix endpoint and return its `data` array. On 401 the cached token is
 * dropped and the request is retried once with a fresh token.
 */
async function helixGet<T>(
  creds: TwitchCredentials,
  path: string,
  params: Record<string, string>,
): Promise<T[]> {
  const url = `${apiURL}/${path}?${new URLSearchParams(params)}`
  const send = async (): Promise<Response> =>
    fetch(url, {
      headers: {
        Authorization: `Bearer ${await getAppAccessToken(creds)}`,
        'Client-Id': creds.clientId,
      },
    })

  let rsp = await send()
  if (rsp.status === 401) {
    console.warn(
      'Got 401 from Twitch API, refreshing access token and retrying',
    )
    await redis.del(tokenKey)
    rsp = await send()
  }
  if (!rsp.ok) {
    throw Error(`Twitch API GET ${path} → ${rsp.status}: ${await rsp.text()}`)
  }
  return ((await rsp.json()) as {data: T[]}).data
}

/** Current stream info for a channel, or undefined if offline. */
export async function getStream(
  creds: TwitchCredentials,
  channel: string,
): Promise<LiveStream | undefined> {
  const [stream] = await helixGet<{
    user_id: string
    game_name: string
    started_at: string
  }>(creds, 'streams', {user_login: channel})
  if (!stream) return
  return {
    broadcasterId: stream.user_id,
    gameName: stream.game_name,
    startedAt: stream.started_at,
  }
}

/** The top clip for a broadcaster since a given time. */
export async function getTopClip(
  creds: TwitchCredentials,
  broadcasterId: string,
  startedAt: string,
): Promise<Clip | undefined> {
  const [clip] = await helixGet<{
    title: string
    url: string
    creator_name: string
  }>(creds, 'clips', {
    broadcaster_id: broadcasterId,
    started_at: startedAt,
    first: '1',
  })
  if (!clip) {
    console.warn(
      `No clips found for broadcaster ${broadcasterId} since ${startedAt}`,
    )
    return
  }
  return {title: clip.title, url: clip.url, creatorName: clip.creator_name}
}

/** URL of the most recent VOD for a broadcaster. */
export async function getLatestVodUrl(
  creds: TwitchCredentials,
  broadcasterId: string,
): Promise<string | undefined> {
  const [vod] = await helixGet<{url: string}>(creds, 'videos', {
    user_id: broadcasterId,
    type: 'archive',
    first: '1',
  })
  if (!vod) console.warn(`No VODs found for broadcaster ${broadcasterId}`)
  return vod?.url
}
