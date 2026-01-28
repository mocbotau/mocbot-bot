# General Maintenance

MOCBOT is susceptible to breakages often due to YouTube's constant updating of their encryption algorithms. If MOCBOT suddenly starts refusing to play tracks, often with Lavalink logging issues such as `Something went wrong when playing the track` or `track is unavailable`, look into updating the following dependencies, in order of most likely candidates to least likely. **Keep in mind any update to the Lavalink server will require a manual pod deletion, as it is deployed as a stateful set**.

### yt-cipher

[`yt-cipher`](https://github.com/kikkia/yt-cipher) is a small, dedicated service for resolving and decrypting YouTube's algorithms.

Both the `docker-compose.yaml` and the main deployment are set up to pull from the repo's master branch, so a simple restart/deletion of the respective pod will retrieve the latest version.

### Lavalink YouTube plugin

This is a [separate plugin](https://github.com/lavalink-devs/youtube-source) that the Lavalink team have separated out from the main Lavalink instance to allow for more frequent updates to work with YouTube. Since they have now offloaded deciphering work to the `yt-cipher` server, this plugin now requires less updates, but may still be a possible fix.

To update, in the [`application.template.yaml`](../lavalink/application.template.yaml), locate the following lines and substitute the version for the latest available version:

```yaml
plugins:
  - dependency: "dev.lavalink.youtube:youtube-plugin:1.17.0"
    snapshot: false
```

If you have an `application.yaml.local`, be sure to update that too.

If there is a dev snapshot that fixes a particular issue, you can change `snapshot: false` to `true` and replace the version tag with a commit hash.

### Lavalink version

This is relatively unlikely to have any effect, but if [Lavalink](https://github.com/lavalink-devs/Lavalink) itself has an update, might be worth upgrading anyway.

In [`values.yaml.gotmpl`](../infra/values.yaml.gotmpl), locate the following lines and update the image version tag:

```yaml
statefulSets:
  - name: "lavalink"
    image: "ghcr.io/lavalink-devs/lavalink:4"
```

Repeat the same in the [`docker-compose.yaml`](../docker-compose.yaml):

```yaml
lavalink:
  image: ghcr.io/lavalink-devs/lavalink:4.1.2-alpine
  restart: unless-stopped
```

### LavaSrc plugin

This has no direct effect on YouTube playback, but may with Spotify playback. Worth a check anyway, but it hasn't been updated in a little while. [Repo](https://github.com/topi314/LavaSrc).

In [`application.template.yaml`](../lavalink/application.template.yaml):

```yaml
- dependency: "com.github.topi314.lavasrc:lavasrc-plugin:4.8.1"
  repository: "https://maven.lavalink.dev/releases"
  snapshot: false
```

Repeat as necessary if you have a local application yaml file.
