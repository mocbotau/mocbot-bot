# Track Play Archival & Validity Semantics

## Context

MOCBOT supports multiple playback features (autoplay, looping, previous, playnow, queue manipulation, website playback) across different clients.
To enable accurate recents, recommendations, and future analytics (e.g. _MOCBOT Wrapped_), the system must:

- Avoid duplicate archive entries caused by looping or replay
- Correctly handle skips, seeks, pauses, and rewinds
- Distinguish accidental plays from meaningful listens
- Remain idempotent under retries and repeated events
- Share identical behaviour across all clients (Discord bot, website)

Earlier designs tied archival logic too closely to commands or wall-clock time, which made edge cases hard to reason about.

---

## Decision

We model **track plays as provisional listen opportunities** that may later become **confirmed listen facts**, using explicit identity and idempotency.

This decision defines the lifecycle, invariants, and rules governing sessions, track plays, and archival validity.

---

## Definitions

- **Session**
  A logical container for playback activity while the bot is connected.

- **Track object**
  An in-memory playback object managed by the music service.

- **Archive entry (track_play)**
  A database record representing a _potential_ or _confirmed_ listen.

- **archive_id**
  The identifier of a track_play, attached to the Track object.

- **Valid listen**
  A listen that exceeds the configured confirmation threshold.

---

## Lifecycle & Rules

### 1. Session creation

- A session is created when the bot joins a voice channel.
- A session represents _potential_ listening activity.

---

### 2. Track start

- When a track starts playing:

  - If the Track object **does not have an `archive_id`**, a provisional track_play is created and its ID is stored in the Track metadata.
  - If the Track object **already has an `archive_id`**, no new archive entry is created.

This ensures **one archive entry per playback chain**.

---

### 3. Progress tracking

- The bot tracks consumed playback time using Lavalink `player_update` events.
- Stored position represents **consumed audio**, not wall-clock time.
- Pauses, seeks, rewinds, and fast-forwards are naturally handled.

---

### 4. Validity threshold

A track play is considered **valid** if:

- Played duration ≥ `min(30 seconds, 15% of track duration)`
- Tracks shorter than 30 seconds are _always_ considered invalid for signal purposes

---

### 5. Track end handling

When a `track_end` event fires (natural end, skip, disconnect, removal):

- If an `archive_id` exists, the bot notifies the API with the final played duration.

The API then applies the following logic:

#### a. Valid listen

- The track_play is confirmed:

  - `ended_at` is set
  - `is_valid = true`

- The `archive_id` **remains associated with the Track object**
- Further updates to this archive entry are **idempotent no-ops**

#### b. Invalid listen

- The track_play is retained with:

  - `is_valid = false`

- The `archive_id` is **removed from the Track object**
- This allows the same track to qualify later if replayed intentionally

---

### 6. Replay, previous, looping semantics

- If a Track object still carries an `archive_id`, it is **always reused**.
- Confirmed archive entries are **never duplicated**, even if:

  - the track is looped
  - the user presses previous
  - the track is resumed after interruption

- Queue looping is naturally idempotent because the same Track objects circulate.

Re-adding the _same song_ as a **new Track object** creates a new archive entry and may be counted again.

---

### 7. Session cleanup

- When a session ends:

  - If the session contains **no valid track plays**, the session is deleted.
  - Sessions with at least one valid track play are retained.

---

### 8. Recents behaviour

- A track appears in `/recents` **only if**:

  - `ended_at IS NOT NULL`
  - `is_valid = true`

Invalid or provisional plays are never shown.

---

### 9. Short tracks & analytics

- Tracks shorter than 30 seconds:

  - Are marked `is_valid = false`
  - Do **not** contribute to recents or recommendations
  - Are retained for analytics and Wrapped-style features

Validity is **classification**, not deletion.

---

## Invariants

The system guarantees:

1. A Track object produces **at most one archive entry**
2. Confirmed archive entries are **never duplicated**
3. Archive updates are **idempotent**
4. Looping and previous cannot inflate stats
5. Short or accidental listens do not pollute recommendations
6. Meaningful replays are counted again only when re-queued as new Track objects

---

## Consequences

### Positive

- Eliminates duplicate archive entries
- Handles all playback edge cases consistently
- Enables future analytics (Wrapped) without harming recommendations
- Keeps bot and website behaviour identical
- Simplifies reasoning and testing

### Trade-offs

- Slightly more state is retained in the database
- Validity must be explicitly filtered in queries
- Lavalink's player update events fire every 5 seconds or so, so the granularity is not perfect here

These trade-offs are intentional and acceptable.

---

## Notes

This ADR intentionally models **listens as facts**, not events.
Playback actions may repeat; confirmed listens do not.
