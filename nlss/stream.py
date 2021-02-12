from twitch import TwitchClient
import twitch
import os
import datetime
from dotenv import load_dotenv
load_dotenv()
twitch_id = os.environ.get("twitch_id")
twitch_access_token = os.environ.get("twitch_access_token")

client = twitch.TwitchHelix(client_id=twitch_id,
                            oauth_token=twitch_access_token)

# x = (client.get_streams(user_logins="DumbDog"))
# print(x[0]["game_name"])
# print(client.get_users(login_names="Northernlion")[0]["id"])


class Stream:
    def __init__(self, channel, live=False):
        self.channel = channel
        self.id = client.get_users(login_names=self.channel)[0]["id"]
        self.live = live
        self.start = None
        self.docket = []
        self.link = f"https://twitch.tv/{self.channel}"

    def liveCheck(self):
        live = client.get_streams(user_logins=self.channel)
        if live:
            self.live = True
        else:
            self.live = False

    def setStart(self):
        date = datetime.datetime.utcnow()
        date = date.replace(second=0, microsecond=0)  # remove seconds
        date = date.isoformat("T") + "Z"  # convert to RFC3339
        self.start = date

    def updateDocket(self):
        info = client.get_streams(user_logins=self.channel)
        if info:
            game_name = info[0]["game_name"]
            self.docket.append(game_name)

    def cleanDocket(self):
        self.docket = self.deleteUnique()
        self.docket = self.deleteRepeats()

    def deleteUnique(self):
        gameArray = self.docket
        for index in range(len(gameArray) - 1, -1, -1):
            if gameArray.count(gameArray[index]) == 1:
                del gameArray[index]
        return gameArray

    def deleteRepeats(self):
        gameArray = self.docket
        # Create an empty list to store unique elements
        uniqueList = []

        # Iterate over the original list and for each element
        # add it to uniqueList, if its not already there.
        for game in gameArray:
            if game not in uniqueList:
                uniqueList.append(game)

        # Return the list of unique elements
        return uniqueList

    def findVOD(self):
        info = client.get_videos(
            user_id=self.id, period="day", page_size=1, sort="trending")
        self.vod = info[0]["url"]

    def findClip(self):
        info = client.get_clips(broadcaster_id=self.id,
                                page_size=1, started_at=self.start)
        self.clipURL = info[0]["url"]
        self.clipTitle = info[0]["title"]
        self.clipAuthor = info[0]["creator_name"]

    def __str__(self):
        return f"Streamer: {self.channel}\nDocket: {self.docket}\nVOD: {self.vod}\nClip: {self.clipURL} {self.clipTitle} {self.clipAuthor}"
