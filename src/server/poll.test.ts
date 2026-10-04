import assert from 'node:assert/strict'
import {beforeEach, test} from 'node:test'
import type {T3} from '@devvit/web/shared'
import type {Clip} from './format.ts'
import {finalizeDelayMs, type PollDeps, poll} from './poll.ts'
import type {StreamState} from './state.ts'
import type {LiveStream} from './twitch.ts'

type Fake = PollDeps & {
  stream: LiveStream | undefined
  state: StreamState | undefined
  clock: number
  clip: Clip | undefined
  vodUrl: string | undefined
  created: {title: string; body: string}[]
  updates: {threadId: T3; body: string}[]
}

let fake: Fake

beforeEach(() => {
  fake = {
    channel: 'Northernlion',
    restartGracePeriodMs: 30 * 60_000,
    stream: undefined,
    state: undefined,
    clock: Date.parse('2026-10-05T18:00:00Z'),
    clip: undefined,
    vodUrl: undefined,
    created: [],
    updates: [],
    now: () => new Date(fake.clock),
    getStream: async () => fake.stream,
    getTopClip: async () => fake.clip,
    getLatestVodUrl: async () => fake.vodUrl,
    createThread: async (title, body) => {
      fake.created.push({title, body})
      return `t3_${fake.created.length}` as T3
    },
    updateThread: async (threadId, body) => {
      fake.updates.push({threadId, body})
    },
    loadState: async () => fake.state,
    saveState: async state => {
      fake.state = structuredClone(state)
    },
  }
})

function live(gameName: string): LiveStream {
  return {
    broadcasterId: '14371185',
    gameName,
    startedAt: '2026-10-05T17:59:00Z',
  }
}

function advance(ms: number): void {
  fake.clock += ms
}

test('creates a thread when the stream goes live', async () => {
  fake.stream = live('The Binding of Isaac: Repentance')
  await poll(fake)

  assert.equal(fake.created.length, 1)
  assert.equal(
    fake.created[0]?.title,
    'Stream Discussion Thread -- Monday, October 05, 2026',
  )
  assert.ok(
    fake.created[0]?.body.includes('* The Binding of Isaac: Repentance'),
  )
  assert.deepEqual(fake.state, {
    threadId: 't3_1',
    broadcasterId: '14371185',
    docket: ['The Binding of Isaac: Repentance'],
    streamStart: '2026-10-05T17:59:00Z',
    isLive: true,
  })
})

test('creates a thread with an empty docket when no game is set', async () => {
  fake.stream = live('')
  await poll(fake)
  assert.ok(fake.created[0]?.body.includes('No games detected yet'))
  assert.deepEqual(fake.state?.docket, [])
})

test('does nothing while offline with no thread', async () => {
  await poll(fake)
  assert.equal(fake.created.length, 0)
  assert.equal(fake.updates.length, 0)
  assert.equal(fake.state, undefined)
})

test('does not edit the thread when nothing changed', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  advance(60_000)
  await poll(fake)
  assert.equal(fake.created.length, 1)
  assert.equal(fake.updates.length, 0)
})

test('adds a new game to the docket', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = live('Slay the Spire')
  advance(60_000)
  await poll(fake)

  assert.equal(fake.updates.length, 1)
  assert.ok(fake.updates[0]?.body.includes('* Isaac\n* Slay the Spire'))
  assert.deepEqual(fake.state?.docket, ['Isaac', 'Slay the Spire'])
})

test('adds the first game once it appears', async () => {
  fake.stream = live('')
  await poll(fake)
  fake.stream = live('Isaac')
  advance(60_000)
  await poll(fake)
  assert.deepEqual(fake.state?.docket, ['Isaac'])
})

test('re-adds a game played again after another', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = live('Just Chatting')
  await poll(fake)
  fake.stream = live('Isaac')
  await poll(fake)
  assert.deepEqual(fake.state?.docket, ['Isaac', 'Just Chatting', 'Isaac'])
})

test('waits before finalizing an offline stream', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  advance(60_000)
  await poll(fake)

  assert.equal(fake.updates.length, 0)
  assert.equal(fake.state?.isLive, true)
  assert.equal(fake.state?.offlineSince, '2026-10-05T18:01:00.000Z')

  advance(finalizeDelayMs - 1)
  await poll(fake)
  assert.equal(fake.updates.length, 0)
})

test('finalizes the thread with the clip and VOD', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  fake.clip = {
    title: 'Great Clip',
    url: 'https://clips.twitch.tv/x',
    creatorName: 'clipper42',
  }
  fake.vodUrl = 'https://www.twitch.tv/videos/123'
  advance(finalizeDelayMs)
  await poll(fake)

  assert.equal(fake.updates.length, 1)
  const body = fake.updates[0]?.body ?? ''
  assert.ok(body.includes('Post Stream Discussion Thread'))
  assert.ok(body.includes('Great Clip'))
  assert.ok(body.includes('https://www.twitch.tv/videos/123'))
  assert.equal(fake.state?.isLive, false)
  assert.equal(fake.state?.offlineSince, undefined)
  assert.equal(fake.state?.endedAt, '2026-10-05T18:02:00.000Z')

  // Already finalized: later offline polls are no-ops.
  advance(60_000)
  await poll(fake)
  assert.equal(fake.updates.length, 1)
})

test('finalizes even when the clip and VOD lookups fail', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  fake.getTopClip = async () => {
    throw Error('clips down')
  }
  fake.getLatestVodUrl = async () => {
    throw Error('videos down')
  }
  advance(finalizeDelayMs)
  await poll(fake)

  assert.equal(fake.updates.length, 1)
  assert.ok(!fake.updates[0]?.body.includes('Twitch VOD'))
  assert.equal(fake.state?.isLive, false)
})

test('retries finalization when the edit fails', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  advance(finalizeDelayMs)
  const updateThread = fake.updateThread
  fake.updateThread = async () => {
    throw Error('reddit down')
  }
  await assert.rejects(poll(fake))
  assert.equal(fake.state?.isLive, true)

  fake.updateThread = updateThread
  advance(60_000)
  await poll(fake)
  assert.equal(fake.state?.isLive, false)
})

test('cancels finalization if the stream comes back', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  fake.stream = live('Isaac')
  advance(60_000)
  await poll(fake)

  assert.equal(fake.state?.isLive, true)
  assert.equal(fake.state?.offlineSince, undefined)
  fake.stream = undefined
  advance(finalizeDelayMs - 1)
  await poll(fake)
  assert.equal(fake.updates.length, 0)
})

test('reuses the thread when the stream restarts within the grace period', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  advance(finalizeDelayMs)
  await poll(fake)

  fake.stream = live('Balatro')
  advance(10 * 60_000)
  await poll(fake)

  assert.equal(fake.created.length, 1)
  const body = fake.updates.at(-1)?.body ?? ''
  assert.equal(fake.updates.at(-1)?.threadId, 't3_1')
  assert.ok(body.includes('[LIVE!]'))
  assert.ok(body.includes('* Isaac\n* Balatro'))
  assert.equal(fake.state?.isLive, true)
  assert.equal(fake.state?.endedAt, undefined)
  assert.equal(fake.state?.streamStart, '2026-10-05T17:59:00Z')
})

test('creates a new thread after the grace period', async () => {
  fake.stream = live('Isaac')
  await poll(fake)
  fake.stream = undefined
  await poll(fake)
  advance(finalizeDelayMs)
  await poll(fake)

  fake.stream = {...live('Balatro'), startedAt: '2026-10-06T18:00:00Z'}
  advance(fake.restartGracePeriodMs)
  await poll(fake)

  assert.equal(fake.created.length, 2)
  assert.equal(fake.state?.threadId, 't3_2')
  assert.deepEqual(fake.state?.docket, ['Balatro'])
  assert.equal(fake.state?.streamStart, '2026-10-06T18:00:00Z')
})
