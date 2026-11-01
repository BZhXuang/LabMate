"""Domain enums for LabMate intent, routing, documents and tool risk."""

from enum import Enum


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class IntentLabel(str, Enum):
    GREETING = "greeting"
    CHITCHAT = "chitchat"
    FAQ_POLICY = "faq_policy"
    HUMAN_HANDOFF = "human_handoff"
    LAB_EQUIPMENT = "lab_equipment"
    LAB_BOOKING = "lab_booking"
    LAB_MAINTENANCE = "lab_maintenance"
    LAB_SAFETY = "lab_safety"
    OUT_OF_SCOPE = "out_of_scope"


class RetrievalStrategy(str, Enum):
    """LabMate routing targets.

    DIRECT: parametric / greeting answers, no retrieval.
    SINGLE: one-shot hybrid retrieval.
    MULTI: Self-RAG iterative retrieval for multi-hop questions.
    AGENT: planner + tools, optionally with retrieval.
    REFUSE: query boundary / policy refusal.
    """

    DIRECT = "direct"
    SINGLE = "single"
    MULTI = "multi"
    AGENT = "agent"
    REFUSE = "refuse"


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    SINGLE_HOP = "single_hop"
    MULTI_HOP = "multi_hop"
    TOOL_REQUIRED = "tool_required"
    OUT_OF_SCOPE = "out_of_scope"


class ToolRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"


class CompressionLevel(str, Enum):
    NONE = "none"
    SOFT_TRUNCATE = "soft_truncate"
    HARD_COMPRESS = "hard_compress"
    AUTO_COMPACT = "auto_compact"


class DocumentCategory(str, Enum):
    FAQ = "faq"
    LAB_SAFETY = "lab_safety"
    LAB_OPERATIONS = "lab_operations"
