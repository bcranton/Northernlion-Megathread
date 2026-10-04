import {reddit} from '@devvit/web/server'
import type {T3} from '@devvit/web/shared'

export type ThreadConfig = {
  subredditName: string
  flairText: string
  flairCssClass: string
  /** Usernames (besides the app account) whose stickied threads get unpinned. */
  legacyBotUsernames: readonly string[]
}

// Community Highlights (new Reddit) can backfill into the two legacy sticky
// slots when one is removed, so unpinning repeats until a pass finds nothing.
// Bounded so a misbehaving listing can't loop forever.
const maxUnpinPasses = 5

/** Unpin any stickied posts in the subreddit made by the bot accounts. */
async function unpinOwnStickies(config: ThreadConfig): Promise<void> {
  const appUser = await reddit.getAppUser()
  const owners = new Set(
    [appUser?.username ?? '', ...config.legacyBotUsernames]
      .filter(Boolean)
      .map(name => name.toLowerCase()),
  )

  for (let pass = 0; pass < maxUnpinPasses; pass++) {
    // Stickied posts are always listed first in hot.
    const posts = await reddit
      .getHotPosts({subredditName: config.subredditName, limit: 10})
      .all()
    const own = posts.filter(
      post => post.stickied && owners.has(post.authorName.toLowerCase()),
    )
    if (!own.length) return
    for (const post of own) {
      await post.unsticky()
      console.log(`Unpinned previous thread id=${post.id}`)
    }
  }
}

/** Create, sticky and flair a new thread. Returns the post ID. */
export async function createThread(
  config: ThreadConfig,
  title: string,
  body: string,
): Promise<T3> {
  await unpinOwnStickies(config)

  const post = await reddit.submitPost({
    subredditName: config.subredditName,
    title,
    text: body,
  })
  console.log(`Created Reddit thread: ${title} (id=${post.id})`)

  // The thread exists now; a failure here must not lose its ID or the next
  // poll would post a duplicate.
  try {
    await post.sticky()
    await reddit.setPostFlair({
      subredditName: config.subredditName,
      postId: post.id,
      text: config.flairText,
      cssClass: config.flairCssClass,
    })
  } catch (err) {
    console.error(`Failed to sticky or flair thread id=${post.id}: ${err}`)
  }
  return post.id
}

/** Replace an existing thread's body. */
export async function updateThread(threadId: T3, body: string): Promise<void> {
  const post = await reddit.getPostById(threadId)
  await post.edit({text: body})
  console.log(`Updated Reddit thread id=${threadId}`)
}
