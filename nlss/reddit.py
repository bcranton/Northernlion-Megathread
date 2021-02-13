import os
from datetime import datetime
from datetime import date
import praw
from dotenv import load_dotenv
load_dotenv()
reddit_id = os.environ.get("reddit_id")
reddit_secret = os.environ.get("reddit_secret")
reddit_password = os.environ.get("reddit_password")


sub = "NLSSBotTest"


class Construct():
    def __init__(self, docket, vod, clipURL, clipTitle, clipAuthor):
        self.docket = docket
        self.vod = vod
        self.clipURL = clipURL
        self.clipTitle = clipTitle
        self.clipAuthor = clipAuthor

        self.constructTitle()
        self.constructBody()

    def constructTitle(self):
        todayDate = date.today().strftime("%B %d, %Y")
        day = datetime.now()
        day = day.strftime("%A")
        title = f"Post Stream Discussion Thread -- {day}, {todayDate}"
        self.title = title

    def constructBody(self):
        header = "# Post Stream Discussion Thread\n\n---------------------------------------------\n\n"

        # Section of the body that contains the docket
        docket = "### Docket\n"
        games = self.docket
        for game in games:
            docket = docket + f"* {game}\n"
        docket = docket + "\n\n"

        # Today's top clip
        clip = None
        try:
            clip = f"\n*Today's Top Clip:*\n"
            clip = clip + f"\n**[{self.clipTitle}]({self.clipURL})**\n"
            clip = clip + \
                f"\n^^^Clipped ^^^by ^^^Twitch ^^^user ^^^[{self.clipAuthor}](https://twitch.tv/{self.clipAuthor})\n\n"
        except:
            pass

        # Slap in the twitch vod link
        vodText = f"\n----------------------------------------------\n\n### [Twitch VOD]({self.vod})\n\n"
        # Link to past threads
        past = "### [Previous Mega Threads](https://www.reddit.com/r/northernlion/search?q=flair%3AMEGA+THREAD&sort=new&restrict_sr=on&t=a)"

        footer = "\n\n----------------------------------------------\n\n^(^^Bot ^^created ^^by ) ^^^[/u/AManNamedLear](https://www.reddit.com/u/AManNamedLear) ^(^^| ^^Find ^^me ^^on) ^^^[GitHub](https://github.com/bcranton/Northernlion-Megathread)"
        # Mash 'em all together
        body = header + docket + clip + vodText + past + footer
        self.body = body

    def getBody(self):
        return self.body


def post(stream):
    # Make sure we can establish a connection to reddit
    connected = False
    while not connected:
        try:
            reddit = praw.Reddit(client_id=reddit_id,
                                 client_secret=reddit_secret,
                                 password=reddit_password,
                                 user_agent='NLSS Bot by /u/AManNamedLear',
                                 username='NorthernlionBot')
            connected = True
        except:
            import time
            time.sleep(30)
            pass

    print(reddit.user.me())
    subreddit = reddit.subreddit(sub)

    content = Construct(stream.docket, stream.vod,
                        stream.clipURL, stream.clipTitle, stream.clipAuthor)

    post = subreddit.submit(content.title, selftext=content.body)
    post.mod.sticky()
    post.mod.flair(text="[MEGA THREAD]", css_class="mega")
    return True
