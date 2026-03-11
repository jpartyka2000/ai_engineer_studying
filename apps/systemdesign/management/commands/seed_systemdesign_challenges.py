"""Management command to seed system design challenges."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.subjects.models import Subject
from apps.systemdesign.models import SystemDesignChallenge


CHALLENGES = [
    {
        "title": "Design Twitter",
        "difficulty": "advanced",
        "description": """Design a social media platform similar to Twitter that allows users to post short messages (tweets), follow other users, and view a timeline of tweets from users they follow.

The system should handle hundreds of millions of users and billions of tweets per day.""",
        "functional_requirements": [
            "Users can post tweets (up to 280 characters)",
            "Users can follow/unfollow other users",
            "Users can view their home timeline (tweets from followed users)",
            "Users can view a user's profile and their tweets",
            "Users can like and retweet posts",
            "Users can search for tweets and users",
            "Real-time notifications for mentions and interactions",
        ],
        "non_functional_requirements": [
            "High availability (99.99% uptime)",
            "Low latency for timeline generation (< 200ms)",
            "Support 500M daily active users",
            "Handle 100K tweets per second at peak",
            "Eventual consistency is acceptable for timeline",
        ],
        "constraints": [
            "Must be globally distributed",
            "Budget allows for significant infrastructure investment",
            "Read-heavy workload (read:write ratio ~ 1000:1)",
        ],
        "reference_components": [
            "load_balancer",
            "api_gateway",
            "user_service",
            "tweet_service",
            "timeline_service",
            "fanout_service",
            "notification_service",
            "search_service",
            "cache_cluster",
            "message_queue",
            "database_sharded",
            "cdn",
            "object_storage",
        ],
        "reference_solution_description": """A Twitter-like system uses a hybrid push-pull model for timeline generation. For users with few followers, tweets are fanned out (pushed) to follower timelines. For celebrities with millions of followers, tweets are pulled on-demand when followers view their timeline.

Key components include:
- Sharded user and tweet databases for horizontal scaling
- Redis clusters for timeline caching
- Kafka for async fanout and event processing
- Elasticsearch for search functionality
- CDN for media content delivery
- Consistent hashing for cache distribution""",
        "tags": ["social_media", "high_scale", "real_time", "fanout"],
    },
    {
        "title": "Design URL Shortener",
        "difficulty": "beginner",
        "description": """Design a URL shortening service like bit.ly that converts long URLs into short, unique links that redirect to the original URL.

The system should be simple but handle high traffic efficiently.""",
        "functional_requirements": [
            "Users can submit a long URL and receive a shortened URL",
            "Shortened URLs redirect to the original URL",
            "Users can optionally customize their short URL",
            "Track click statistics (count, referrer, location)",
            "URLs can have optional expiration dates",
        ],
        "non_functional_requirements": [
            "High availability (99.9% uptime)",
            "Very low latency for redirects (< 50ms)",
            "Support 100M URLs created per month",
            "Handle 10B redirects per month",
            "Shortened URLs should be as short as possible",
        ],
        "constraints": [
            "Short URLs should be 7-8 characters",
            "No offensive words in generated URLs",
            "URLs should not be predictable/guessable",
        ],
        "reference_components": [
            "load_balancer",
            "api_server",
            "key_generation_service",
            "database",
            "cache",
            "analytics_service",
        ],
        "reference_solution_description": """A URL shortener uses Base62 encoding (a-z, A-Z, 0-9) to generate short codes. Pre-generating keys in batches avoids collision checking on each request.

Key components:
- Key Generation Service pre-generates unique keys stored in a key database
- Application servers fetch keys in batches for low-latency URL creation
- Redis cache stores popular URL mappings for fast redirects
- SQL database for persistent storage with read replicas
- Analytics pipeline using Kafka for click tracking""",
        "tags": ["beginner", "caching", "encoding", "redirect"],
    },
    {
        "title": "Design Netflix",
        "difficulty": "advanced",
        "description": """Design a video streaming service like Netflix that allows users to browse, search, and stream video content on demand.

The system should deliver high-quality video to millions of concurrent viewers globally.""",
        "functional_requirements": [
            "Users can browse and search for content",
            "Users can stream video on multiple devices",
            "Adaptive bitrate streaming based on network conditions",
            "Personalized recommendations",
            "Continue watching from where they left off",
            "Support multiple user profiles per account",
            "Download content for offline viewing",
        ],
        "non_functional_requirements": [
            "Support 200M subscribers globally",
            "Handle 100K concurrent streams per region",
            "Video start time < 2 seconds",
            "99.99% availability",
            "Support multiple video qualities (480p to 4K)",
        ],
        "constraints": [
            "Content licensing varies by region",
            "Must handle peak load during new content releases",
            "Optimize for bandwidth costs",
        ],
        "reference_components": [
            "cdn",
            "video_encoding_service",
            "content_delivery",
            "api_gateway",
            "user_service",
            "recommendation_engine",
            "search_service",
            "playback_service",
            "analytics",
            "database",
            "cache",
            "object_storage",
        ],
        "reference_solution_description": """Netflix's architecture relies heavily on CDN (Open Connect) to serve video content from edge locations close to users.

Key components:
- Videos transcoded into multiple formats/bitrates and stored in S3
- Open Connect appliances in ISP data centers for local delivery
- Adaptive bitrate streaming (ABR) adjusts quality based on bandwidth
- Microservices architecture for different functions
- Machine learning for personalized recommendations
- Chaos engineering for resilience testing""",
        "tags": ["streaming", "cdn", "video", "recommendation", "high_scale"],
    },
    {
        "title": "Design Uber",
        "difficulty": "advanced",
        "description": """Design a ride-sharing service like Uber that connects drivers with riders in real-time.

The system should efficiently match riders with nearby drivers and handle payments.""",
        "functional_requirements": [
            "Riders can request rides and see nearby drivers",
            "Drivers can accept/reject ride requests",
            "Real-time location tracking during rides",
            "Fare estimation and calculation",
            "Payment processing",
            "Rating system for drivers and riders",
            "Trip history for both parties",
        ],
        "non_functional_requirements": [
            "Matching should complete in < 5 seconds",
            "Location updates every 4 seconds",
            "Support 10M daily rides",
            "High availability in all operating cities",
            "Handle surge pricing during peak times",
        ],
        "constraints": [
            "Must work with intermittent network connectivity",
            "Comply with local transportation regulations",
            "Handle different currencies and payment methods",
        ],
        "reference_components": [
            "load_balancer",
            "api_gateway",
            "rider_service",
            "driver_service",
            "matching_service",
            "location_service",
            "pricing_service",
            "payment_service",
            "notification_service",
            "database",
            "cache",
            "message_queue",
            "geospatial_index",
        ],
        "reference_solution_description": """Uber's system centers on efficient geospatial matching of riders and drivers.

Key components:
- Geospatial indexing using S2 cells or similar for efficient proximity queries
- Real-time location tracking via WebSocket connections
- Matching algorithm considering distance, driver ratings, and vehicle type
- Supply positioning to predict demand and guide drivers
- Dynamic pricing based on supply/demand ratio
- Event-driven architecture for ride lifecycle management""",
        "tags": ["geospatial", "real_time", "matching", "mobile"],
    },
    {
        "title": "Design WhatsApp",
        "difficulty": "intermediate",
        "description": """Design a messaging service like WhatsApp that supports one-on-one and group messaging with real-time delivery.

The system should ensure message delivery even when users are offline.""",
        "functional_requirements": [
            "One-on-one messaging",
            "Group chats (up to 256 members)",
            "Message delivery status (sent, delivered, read)",
            "Media sharing (images, videos, documents)",
            "End-to-end encryption",
            "Online/last seen status",
            "Message history sync across devices",
        ],
        "non_functional_requirements": [
            "Support 2B users",
            "Message delivery latency < 100ms when online",
            "Guaranteed message delivery (at-least-once)",
            "99.99% availability",
            "Support 100B messages per day",
        ],
        "constraints": [
            "Messages stored on servers only until delivered",
            "Must work on low-bandwidth connections",
            "Battery efficiency for mobile clients",
        ],
        "reference_components": [
            "load_balancer",
            "websocket_server",
            "message_service",
            "group_service",
            "presence_service",
            "media_service",
            "notification_service",
            "message_queue",
            "database",
            "cache",
            "object_storage",
        ],
        "reference_solution_description": """WhatsApp uses a connection-oriented architecture with persistent WebSocket connections for real-time delivery.

Key components:
- WebSocket servers maintain persistent connections with clients
- Message queue (Kafka) for reliable message delivery
- Cassandra for message storage (write-optimized)
- Message stored until delivered, then deleted from server
- End-to-end encryption using Signal Protocol
- Push notifications for offline users
- Last Write Wins for conflict resolution""",
        "tags": ["messaging", "real_time", "websocket", "encryption"],
    },
    {
        "title": "Design Google Drive",
        "difficulty": "intermediate",
        "description": """Design a cloud file storage service like Google Drive that allows users to store, sync, and share files across devices.

The system should efficiently handle large files and provide real-time collaboration.""",
        "functional_requirements": [
            "Upload and download files",
            "Automatic sync across devices",
            "File and folder sharing with permission controls",
            "File versioning and history",
            "Search files by name and content",
            "Real-time collaborative editing (like Google Docs)",
            "Offline access to selected files",
        ],
        "non_functional_requirements": [
            "Support files up to 5TB",
            "Upload/download speed limited only by network",
            "Strong consistency for file metadata",
            "99.9% durability (no data loss)",
            "Support 1B users",
        ],
        "constraints": [
            "Efficient storage for similar files (deduplication)",
            "Bandwidth optimization for sync",
            "Comply with data residency requirements",
        ],
        "reference_components": [
            "load_balancer",
            "api_gateway",
            "metadata_service",
            "block_storage_service",
            "sync_service",
            "sharing_service",
            "search_service",
            "notification_service",
            "database",
            "object_storage",
            "cache",
            "message_queue",
        ],
        "reference_solution_description": """Cloud storage systems use block-level deduplication and delta sync to minimize bandwidth and storage.

Key components:
- Files split into blocks (4MB chunks)
- Block-level deduplication using content-based hashing
- Delta sync transfers only changed blocks
- Metadata stored in SQL database with strong consistency
- File content in distributed object storage (multiple replicas)
- Real-time sync using WebSockets
- Operational Transformation for collaborative editing""",
        "tags": ["storage", "sync", "collaboration", "deduplication"],
    },
    {
        "title": "Design Rate Limiter",
        "difficulty": "beginner",
        "description": """Design a rate limiting service that can be used by multiple services to prevent abuse and ensure fair usage.

The rate limiter should support different limiting algorithms and be highly performant.""",
        "functional_requirements": [
            "Limit requests per user/IP/API key",
            "Support different rate limits per API endpoint",
            "Return appropriate headers (remaining quota, reset time)",
            "Support multiple algorithms (fixed window, sliding window, token bucket)",
            "Allow rate limit configuration changes without restart",
            "Provide analytics on rate limit violations",
        ],
        "non_functional_requirements": [
            "Add < 1ms latency to requests",
            "Handle 1M requests per second",
            "Distributed across multiple data centers",
            "Fail-open (allow traffic if rate limiter fails)",
            "Consistent limiting across replicas",
        ],
        "constraints": [
            "Memory-efficient (millions of unique users)",
            "Must not become a single point of failure",
            "Support both synchronous and asynchronous patterns",
        ],
        "reference_components": [
            "rate_limiter_service",
            "configuration_service",
            "distributed_cache",
            "rules_engine",
            "analytics_service",
        ],
        "reference_solution_description": """Rate limiters typically use Redis for distributed counting due to its speed and atomic operations.

Key algorithms:
- Token Bucket: Smooth rate limiting, allows bursts
- Sliding Window Log: Accurate but memory-intensive
- Sliding Window Counter: Balance of accuracy and efficiency

Implementation:
- Redis with Lua scripts for atomic operations
- Local cache for hot rate limit rules
- Eventual consistency acceptable for rate limits
- Graceful degradation to local limiting if Redis fails""",
        "tags": ["beginner", "rate_limiting", "distributed", "redis"],
    },
    {
        "title": "Design News Feed",
        "difficulty": "intermediate",
        "description": """Design a news feed system like Facebook's that shows personalized content from friends and pages a user follows.

The feed should be engaging and update in real-time.""",
        "functional_requirements": [
            "Show posts from friends and followed pages",
            "Rank posts by relevance and recency",
            "Support different content types (text, images, videos, links)",
            "Real-time updates when new posts arrive",
            "Infinite scroll pagination",
            "Allow users to hide/report content",
        ],
        "non_functional_requirements": [
            "Feed generation < 200ms",
            "Support 1B daily active users",
            "Handle 10M new posts per minute",
            "Personalized ranking per user",
            "Fresh content should appear quickly",
        ],
        "constraints": [
            "Balance between relevance and recency",
            "Cannot show duplicate posts",
            "Must handle users following 5000+ friends/pages",
        ],
        "reference_components": [
            "load_balancer",
            "api_gateway",
            "post_service",
            "feed_generation_service",
            "ranking_service",
            "fanout_service",
            "cache",
            "database",
            "message_queue",
            "feature_store",
            "ml_model_service",
        ],
        "reference_solution_description": """News feed systems use a combination of push (fanout) and pull models depending on user follower counts.

Key components:
- Fanout service pushes posts to follower feed caches (for normal users)
- Pull on read for celebrity accounts (too many followers to fanout)
- ML ranking model scores posts based on engagement predictions
- Feature store provides user and post features for ranking
- Feed cache stores pre-ranked feed per user
- Real-time updates via long polling or WebSocket""",
        "tags": ["social_media", "ranking", "fanout", "machine_learning"],
    },
    {
        "title": "Design Web Crawler",
        "difficulty": "intermediate",
        "description": """Design a web crawler like Googlebot that can efficiently crawl the web, discover new pages, and keep content fresh.

The crawler should be polite and respect robots.txt rules.""",
        "functional_requirements": [
            "Crawl web pages starting from seed URLs",
            "Parse HTML to extract links",
            "Respect robots.txt and crawl delays",
            "Detect and handle duplicate content",
            "Prioritize important/fresh pages",
            "Store crawled content for indexing",
        ],
        "non_functional_requirements": [
            "Crawl 1B pages per day",
            "Re-crawl important pages frequently",
            "Distribute load across target domains",
            "Handle various content types and encodings",
            "Fault-tolerant (continue if some crawlers fail)",
        ],
        "constraints": [
            "Be polite - don't overload websites",
            "Handle JavaScript-rendered content",
            "Manage bandwidth costs",
        ],
        "reference_components": [
            "url_frontier",
            "crawler_workers",
            "dns_resolver",
            "html_parser",
            "content_store",
            "url_deduplication",
            "robots_txt_cache",
            "scheduler",
            "message_queue",
        ],
        "reference_solution_description": """Web crawlers use a frontier of URLs to crawl, prioritized by importance and freshness requirements.

Key components:
- URL Frontier maintains queue of URLs to crawl, prioritized by domain importance
- Distributed workers fetch pages in parallel
- Politeness enforcer ensures crawl delay per domain
- Consistent hashing assigns URLs to workers by domain
- Content seen filter using Bloom filter or MinHash for deduplication
- Parser extracts links and content for storage
- Scheduler determines recrawl frequency based on page change rate""",
        "tags": ["crawler", "distributed", "parsing", "scheduling"],
    },
    {
        "title": "Design Notification System",
        "difficulty": "beginner",
        "description": """Design a notification system that can send notifications through multiple channels (push, email, SMS) at scale.

The system should handle millions of notifications reliably.""",
        "functional_requirements": [
            "Send notifications via push, email, and SMS",
            "Support scheduled notifications",
            "Allow users to configure notification preferences",
            "Track delivery status",
            "Support notification templates",
            "Rate limiting per user to prevent spam",
        ],
        "non_functional_requirements": [
            "Send 10M notifications per day",
            "Delivery within 30 seconds for real-time notifications",
            "At-least-once delivery guarantee",
            "99.9% delivery success rate",
            "Handle traffic spikes (10x normal load)",
        ],
        "constraints": [
            "Comply with regulations (CAN-SPAM, GDPR)",
            "Integrate with third-party providers (FCM, APNS, SendGrid, Twilio)",
            "Cost-effective (SMS is expensive)",
        ],
        "reference_components": [
            "api_gateway",
            "notification_service",
            "template_service",
            "preference_service",
            "delivery_workers",
            "push_provider",
            "email_provider",
            "sms_provider",
            "message_queue",
            "database",
            "scheduler",
        ],
        "reference_solution_description": """Notification systems use message queues to decouple notification creation from delivery.

Key components:
- Notification service validates and queues notifications
- Priority queues separate urgent from batch notifications
- Channel-specific workers handle delivery to each provider
- Retry logic with exponential backoff for failures
- Preference service filters based on user settings
- Template service renders personalized content
- Tracking service logs delivery status""",
        "tags": ["beginner", "messaging", "multi_channel", "async"],
    },
]


class Command(BaseCommand):
    """Seed the database with system design challenges."""

    help = "Seed the database with system design challenges"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing challenges before seeding",
        )
        parser.add_argument(
            "--enable-subject",
            action="store_true",
            help="Enable System Design mode for the system-design subject",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = SystemDesignChallenge.objects.filter(source="manual").count()
            SystemDesignChallenge.objects.filter(source="manual").delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing challenges"))

        created_count = 0
        updated_count = 0

        for challenge_data in CHALLENGES:
            slug = slugify(challenge_data["title"])

            defaults = {
                "title": challenge_data["title"],
                "description": challenge_data["description"],
                "difficulty": challenge_data["difficulty"],
                "functional_requirements": challenge_data["functional_requirements"],
                "non_functional_requirements": challenge_data["non_functional_requirements"],
                "constraints": challenge_data["constraints"],
                "reference_components": challenge_data["reference_components"],
                "reference_solution_description": challenge_data["reference_solution_description"],
                "tags": challenge_data["tags"],
                "source": "manual",
                "is_active": True,
            }

            challenge, created = SystemDesignChallenge.objects.update_or_create(
                slug=slug,
                defaults=defaults,
            )

            if created:
                created_count += 1
                self.stdout.write(f"  Created: {challenge.title}")
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {challenge.title}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeded {created_count} new challenges, updated {updated_count} existing"
            )
        )

        # Enable System Design mode for the system-design subject
        if options["enable_subject"]:
            try:
                subject = Subject.objects.get(slug="system-design")
                subject.supports_systemdesign = True
                subject.save(update_fields=["supports_systemdesign"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Enabled System Design mode for '{subject.name}' subject"
                    )
                )
            except Subject.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        "Subject 'system-design' not found. Create it first or run with --enable-subject later."
                    )
                )
