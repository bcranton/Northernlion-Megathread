import {redis} from '@devvit/web/server'
import type {T3} from '@devvit/web/shared'

/** The most recent stream and its thread. */
export type StreamState = {
  threadId: T3
  broadcasterId: string
  docket: string[]
  /** When the stream started, per Twitch. Clips are fetched from this time. */
  streamStart: string
  isLive: boolean
  /** When the stream was first seen offline; finalization waits on this. */
  offlineSince?: string | undefined
  /** When the thread was finalized. */
  endedAt?: string | undefined
}

const stateKey = 'stream:state'
const lockKey = 'stream:poll-lock'

export async function loadState(): Promise<StreamState | undefined> {
  const json = await redis.get(stateKey)
  return json ? (JSON.parse(json) as StreamState) : undefined
}

export async function saveState(state: Readonly<StreamState>): Promise<void> {
  await redis.set(stateKey, JSON.stringify(state))
}

/**
 * Take the poll lock so overlapping scheduler runs can't both create a thread.
 * Returns false if another run holds it. The lock expires on its own in case a
 * run dies without releasing it.
 */
export async function acquirePollLock(): Promise<boolean> {
  const token = crypto.randomUUID()
  const expiration = new Date(Date.now() + 55_000)
  await redis.set(lockKey, token, {nx: true, expiration})
  // Read it back rather than relying on SET NX's reply to know who won.
  return (await redis.get(lockKey)) === token
}

export async function releasePollLock(): Promise<void> {
  await redis.del(lockKey)
}
