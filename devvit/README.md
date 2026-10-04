# Northernlion Megathread

Posts and maintains a daily stream discussion thread ("megathread") for
[Northernlion](https://www.twitch.tv/Northernlion)'s Twitch streams.

## What it does

Once a minute the app checks whether the configured Twitch channel is live.

- **Stream goes live:** the app posts a new thread titled
  `Stream Discussion Thread -- <weekday>, <date>` (Vancouver time), pins it,
  applies the megathread flair, and unpins the previous megathread.
- **Game changes:** the new game is added to the thread's docket.
- **Stream ends:** after a two-minute wait for Twitch to publish the VOD and
  clips, the thread's heading changes to "Post Stream Discussion Thread" and
  it gets links to the VOD and the day's top clip.
- **Stream restarts shortly after ending:** if the stream comes back within the
  grace period (30 minutes by default), the same thread is reused instead of
  posting a new one.

It's meant for one subreddit (r/northernlion) and only acts in the subreddit
it's installed in. It doesn't read or store anything about Reddit users.

## Moderator settings

Found under the app's settings for your subreddit:

| Setting | Default | What it does |
| --- | --- | --- |
| Post megathreads | on | Pauses the app without uninstalling it. |
| Twitch channel | `Northernlion` | Channel to watch. |
| Restart grace period (minutes) | `30` | How long after a stream ends a restart reuses the old thread. |
| Thread flair text | `[MEGA THREAD]` | Flair applied to each thread. The "Previous Mega Threads" link searches for this flair. |
| Thread flair CSS class | `mega` | CSS class applied with the flair (old Reddit). |
| Also unpin threads from these accounts | `NorthernlionBot` | Comma-separated usernames whose pinned threads are unpinned along with the app's own, for the handover from the old bot. |

## Developer setup

The app needs a Twitch application's credentials, set once as app secrets
(create one at <https://dev.twitch.tv/console/apps>; no redirect or webhook is
needed):

```sh
npx devvit settings set twitchClientId
npx devvit settings set twitchClientSecret
```

Commands, run from this directory:

- `npm install`: install dependencies.
- `npm run playtest [r/sub]`: build, upload and install on a test subreddit.
- `npm test`: typecheck, lint, unit tests and build.
- `npm run publish`: build, upload and submit for app review.

## Fetch Domains

The following domains are requested for this app:

- `id.twitch.tv` - Gets an app access token (OAuth client credentials) for the
  Twitch API.
- `api.twitch.tv` - Reads public stream status, current game, top clip and
  latest VOD for the configured channel via the Twitch Helix API.

## Data

The app stores only the current thread's ID, the list of games played, and
stream start/end times, in the app's Redis storage. It caches the Twitch access
token there too. See [PRIVACY.md](PRIVACY.md) and [TERMS.md](TERMS.md).
