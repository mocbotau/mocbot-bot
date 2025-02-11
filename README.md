![github_banner_slim](https://github.com/MasterOfCubesAU/MOCBOT/assets/38149391/9f5f850c-cead-4e5e-9cab-ecdf886b6b9a)

[![GPLv3 License](https://img.shields.io/badge/License-GPL%20v3-yellow.svg)](https://opensource.org/licenses/)

# MOCBOT: The Discord Bot

MOCBOT is a discord bot made to solve all your automation needs. MOCBOT allows for automated Discord server management.

Manage MOCBOT configuration through the [MOCBOT Website](https://mocbot.masterofcubesau.com/).

## Authors

- [@MasterOfCubesAU](https://www.github.com/MasterOfCubesAU)
- [@samiam](https://github.com/sam1357)

## Features

- **User XP/Levels** (Voice and Text XP dsitribution, Server Leaderboards, Role Rewards, XP Management)
- **Private Lobbies** (Create your own private lobby and allow specific people to access it)
- **Music** (Play any media from sources like YouTube, Spotify, SoundCloud and Apple Music)
- Music Filters (Spice up your music with some cool effects)
- User Management (Kicks/Bans/Warnings)
- Customisable Announcement Messages
- Channel Purging
- Bot Logging (To be ported)
- User Verification (To be ported)
- Support Tickets (To be ported)

## Usage

Invite MOCBOT into your Discord server [here](https://discord.com/api/oauth2/authorize?client_id=417962459811414027&permissions=8&scope=bot%20applications.commands).

Type `/` in your Discord server to see available commands. Alternatively, you may view all commands [here](https://mocbot.masterofcubesau.com/commands)

## Deployment

MOCBOT is intended to be deployed into Kubernetes via a custom Helm chart. This repository is setup for local development
in an isolated environment using Docker.

## Local Development:

1. `config.yaml` and `.env.local` work together to provide the necessary configuration for MOCBOT, to simulate the environment variables that would be provided
   in the cluster when deployed. `docker-compose.yaml` creates Lavalink and MOCBOT containers, and links them together. All these files should not need changing.
2. Create a `.local-secrets` folder in the root directory of the project. This folder should contain the following files:
   | Filename | Description |
   |--------------------|------------------------------------|
   | `api-key` | The API key to connect to MOCBOT API. Assuming you are running the `MOCBOT-API` repo locally without changes, the default APIKey set in that repo is `test`. |
   | `bot-token` | The token of the Discord bot |
   | `lavalink-password` | The password for the Lavalink server. Take note of this to put in the Lavalink config as well. |
   | `socket-key` | The key that will allow other services to connect to MOCBOT's socket. |
   | `spotify-client-id` | The client ID for the Spotify API. |
   | `spotify-client-secret` | The client secret for the Spotify API. |
3. Copy [`lavalink/application.template.yaml`](./lavalink/application.template.yaml) to `lavalink/application.yaml.local`, and replace any template values with your own. Ensure that
   `lavalink-password` is the same as the one in `.local-secrets/lavalink-password`.

4a. If you already have a YouTube refresh token, you can directly put it into `application.yaml.local`.

4b. If you do not have a YouTube refresh token, comment out the `refreshToken` line in `application.yaml.local`, set `skipInitialization` to `false`
and run `docker compose up -d lavalink` to start the Lavalink server.
Keep an eye on the logs. You will see a message telling you to visit `https://google.com/device` to enter a code. Once done, Lavalink will print out the refresh token.
Copy this token into `application.yaml.local`, and set `skipInitialization` to `true`.

> [!CAUTION]
> DO NOT use your own Google account to generate the refresh token. There is a possibility that the account may be banned from using the YouTube API.
> Use a burner account instead.

5. You will need MOCBOT API running (preferably locally). Clone the repo [here](https://github.com/mocbotau/mocbot-api).
   Follow the instructions in the README to get the API running.

6. Run `docker compose up --build -d` to start the bot.

## Feedback

If you have any feedback, please reach out to us at https://masterofcubesau.com/contact

## License

[GPL v3](https://choosealicense.com/licenses/gpl-3.0/)
