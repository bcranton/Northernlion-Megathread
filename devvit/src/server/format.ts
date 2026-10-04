export type Clip = {title: string; url: string; creatorName: string}

export type ThreadBodyOptions = {
  channel: string
  docket: readonly string[]
  vodUrl?: string | undefined
  clip?: Clip | undefined
  isLive: boolean
}

const titleDateFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Vancouver',
  weekday: 'long',
  month: 'long',
  day: '2-digit',
  year: 'numeric',
})

/** Build the thread title with the given date in Vancouver time. */
export function buildThreadTitle(now: Date): string {
  const parts = Object.fromEntries(
    titleDateFormat.formatToParts(now).map(part => [part.type, part.value]),
  )
  return `Stream Discussion Thread -- ${parts.weekday}, ${parts.month} ${parts.day}, ${parts.year}`
}

/**
 * Build the thread body markdown.
 *
 * Uses blank lines between sections for consistent paragraph breaks.
 * Single newlines within a section keep content together.
 */
export function buildThreadBody(opts: ThreadBodyOptions): string {
  const sections: string[] = []

  // Header
  if (opts.isLive) {
    sections.push('# Stream Discussion Thread')
    sections.push(
      `**The stream is currently [LIVE!](https://www.twitch.tv/${opts.channel})**`,
    )
  } else {
    sections.push('# Post Stream Discussion Thread')
  }

  sections.push('---')

  // Docket
  const docketLines = ['### Docket', '']
  if (opts.docket.length) {
    for (const game of opts.docket) docketLines.push(`* ${game}`)
  } else {
    docketLines.push('*No games detected yet*')
  }
  sections.push(docketLines.join('\n'))

  // Clip (only after stream ends)
  if (opts.clip) {
    const creator = opts.clip.creatorName
    sections.push(
      [
        "*Today's Top Clip:*",
        '',
        `**[${opts.clip.title}](${opts.clip.url})**`,
        '',
        `^(Clipped by Twitch user) [^(${creator})](https://twitch.tv/${creator})`,
      ].join('\n'),
    )
  }

  sections.push('---')

  // VOD
  if (opts.vodUrl) {
    sections.push(`### [Twitch VOD](${opts.vodUrl})`)
  } else if (opts.isLive) {
    sections.push('*VOD will be added after the stream ends.*')
  }

  // Previous threads
  sections.push(
    '### [Previous Mega Threads]' +
      '(https://www.reddit.com/r/northernlion/search?q=flair%3AMEGA+THREAD&sort=new&restrict_sr=on&t=a)',
  )

  // Footer
  sections.push('---')
  sections.push(
    '^(Bot created by) [^(/u/AManNamedLear)](https://www.reddit.com/u/AManNamedLear) ' +
      '^(|) ' +
      '[^(GitHub)](https://github.com/bcranton/Northernlion-Megathread)',
  )

  return sections.join('\n\n')
}
