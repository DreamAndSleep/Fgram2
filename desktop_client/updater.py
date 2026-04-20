import hashlib
import asyncio
import zgram as cl
import sys

CHUNK = 65536


class Updater(cl.Client):

    async def getLatestVersion(self, save_path):

        await self.sendJsonCommand({"command": "LATESTVERSION"})
        response = await self.getJson()

        if not response or response.get("status") != "OK":
            print("Server error")
            return False

        size = int(response["size"])
        print(f"Total size: {round(size / (1024 * 1024), 2)} MB\n")

        await self.send_line("READY")

        received = 0
        sha = hashlib.sha256()

        with open(save_path, "wb") as f:

            while received < size:

                chunk = await self.reader.read(
                    min(CHUNK, size - received)
                )

                if not chunk:
                    raise ConnectionError("Connection closed unexpectedly")

                f.write(chunk)
                sha.update(chunk)

                received += len(chunk)

                # Красивый прогресс-бар
                percent = received / size * 100
                bar_length = 40
                filled_length = int(bar_length * received // size)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                sys.stdout.write(f"\rProgress: |{bar}| {percent:6.2f}% ({received / (1024*1024):.2f}/{size / (1024*1024):.2f} MB)")
                sys.stdout.flush()

        print()  # перенос строки после прогресс-бара

        server_hash = (await self.reader.readline()).decode().strip()

        if server_hash != sha.hexdigest():
            print("Hash mismatch")
            return False

        print("Download completed successfully")
        return True


async def main():

    updater = Updater(cl.Config("config.json"))

    await updater.connect()

    await updater.getLatestVersion("zgram")


asyncio.run(main())