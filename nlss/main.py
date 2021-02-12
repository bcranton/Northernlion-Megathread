import os
import requests
import time
import sys
import stream
import reddit


def main():
    # Init object
    Northernlion = stream.Stream("Northernlion")
    online = False
    # Run infinitely, that way its always monitoring for streams
    print(f"Monitoring {Northernlion.channel}")
    while True:
        # If the channel is live, we start monitoring for what games they are playing
        Northernlion.liveCheck()
        if Northernlion.live:
            if not Northernlion.start:
                Northernlion.setStart()
                print(Northernlion.start)

            online = True
            print("Finding current game...")
            Northernlion.updateDocket()
            print(Northernlion.docket)

        elif online:
            # If the channel was online last time we checked but is no longer
            # Wait 3 minutes to make sure it doesn't come back online
            print("Waiting 3 more minutes to make sure stream doesn't come back...")
            for remaining in range(180, 0, -1):
                sys.stdout.write("\r")
                sys.stdout.write(f"{remaining} seconds remaining...")
                sys.stdout.flush()
                time.sleep(1)
            print()
            Northernlion.liveCheck()
            if not Northernlion.live:
                Northernlion.cleanDocket()
                print(f"Getting vod URL")
                Northernlion.findVOD()
                print(f"Getting top clip")
                Northernlion.findClip()
                print(f"Posting to Reddit")
                reddit.post(Northernlion)

                # Reset variables
                online = False
                del Northernlion
                Northernlion = stream.Stream("Northernlion")

        print("Sleeping for 1 minute before checking again...")
        for remaining in range(60, 0, -1):
            sys.stdout.write("\r")
            sys.stdout.write(f"{remaining} seconds remaining")
            sys.stdout.flush()
            time.sleep(1)
        print()


main()
