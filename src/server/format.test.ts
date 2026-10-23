import assert from 'node:assert/strict'
import {test} from 'node:test'
import {buildThreadBody, buildThreadTitle} from './format.ts'

const channel = 'Northernlion'

test('title uses the Vancouver date', () => {
  // 03:00 UTC on the 28th is still the 27th in Vancouver.
  const title = buildThreadTitle(new Date('2026-02-28T03:00:00Z'))
  assert.equal(title, 'Stream Discussion Thread -- Friday, February 27, 2026')
})

test('title zero-pads the day', () => {
  const title = buildThreadTitle(new Date('2026-03-05T20:00:00Z'))
  assert.equal(title, 'Stream Discussion Thread -- Thursday, March 05, 2026')
})

test('live body with games', () => {
  const body = buildThreadBody({
    channel,
    docket: ['Isaac', 'Slay The Spire'],
    isLive: true,
  })
  assert.match(body, /\[LIVE!\]\(https:\/\/www\.twitch\.tv\/Northernlion\)/)
  assert.ok(body.includes('* Isaac\n* Slay The Spire'))
  assert.ok(body.includes('VOD will be added after the stream ends'))
})

test('live body without games', () => {
  const body = buildThreadBody({channel, docket: [], isLive: true})
  assert.ok(body.includes('No games detected yet'))
})

test('finalized body with clip and VOD', () => {
  const body = buildThreadBody({
    channel,
    docket: ['Isaac'],
    vodUrl: 'https://www.twitch.tv/videos/123',
    clip: {
      title: 'Great Clip',
      url: 'https://clips.twitch.tv/test',
      creatorName: 'clipper42',
    },
    isLive: false,
  })
  assert.ok(body.includes('Post Stream Discussion Thread'))
  assert.ok(!body.includes('LIVE'))
  assert.ok(body.includes('**[Great Clip](https://clips.twitch.tv/test)**'))
  assert.ok(
    body.includes(
      '^(Clipped by Twitch user) [^(clipper42)](https://twitch.tv/clipper42)',
    ),
  )
  assert.ok(body.includes('### [Twitch VOD](https://www.twitch.tv/videos/123)'))
})

test('finalized body without clip or VOD', () => {
  const body = buildThreadBody({channel, docket: ['Isaac'], isLive: false})
  assert.ok(!body.includes('Top Clip'))
  assert.ok(!body.includes('Twitch VOD'))
  assert.ok(!body.includes('VOD will be added'))
})

test('footer and previous threads link are always present', () => {
  const body = buildThreadBody({channel, docket: [], isLive: true})
  assert.ok(body.includes('Previous Mega Threads'))
  assert.ok(body.includes('AManNamedLear'))
  assert.ok(body.includes('GitHub'))
})

test('footer no longer links EggEats', () => {
  const body = buildThreadBody({channel, docket: [], isLive: true})
  assert.ok(!body.toLowerCase().includes('eggeats'))
})

test('sections are separated by blank lines', () => {
  const body = buildThreadBody({channel, docket: ['Isaac'], isLive: true})
  assert.ok(body.includes('\n\n---\n\n'))
})
