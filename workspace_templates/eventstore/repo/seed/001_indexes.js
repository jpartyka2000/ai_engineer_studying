// Runs once, on first boot of an empty Mongo volume.
//
// This file creates the collection and its indexes so that a freshly started stack is
// usable before the application has been touched. It deliberately duplicates
// src/eventstore/mongo.py's INDEX_SPECS rather than replacing it: this script only runs
// on an empty volume, so an environment restored from a backup, or one where somebody
// dropped an index, would never see it. ensure_indexes() in the application is the
// authority; this is the head start.
//
// If you change an index here, change INDEX_SPECS too. A test asserts the two agree.

db = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE || "eventstore");

db.createCollection("events");

// Deduplication. A gateway that retries a batch after a timeout must not double-count.
db.events.createIndex({ event_id: 1 }, { name: "event_id_unique", unique: true });

// The recent-window query: equality on service, descending range on event time.
db.events.createIndex(
  { service: 1, occurred_at: -1 },
  { name: "service_occurred_at" }
);

// The incremental rollup scans by ingest time, not event time.
db.events.createIndex({ received_at: 1 }, { name: "received_at" });

print("eventstore: created events collection and 3 indexes");
