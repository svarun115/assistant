"""
Data models for all journal entities (Event-Centric Architecture)
Using Pydantic for validation and serialization

ARCHITECTURE:
- Events are the primary aggregate root
- Events own WHO (participants), WHERE (location), WHEN (time)
- Workouts, Meals, Sleep, Reflections are specializations that reference events
"""

from datetime import datetime, date, time
from typing import Optional, List, Union
from uuid import UUID, uuid4
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ============================================================================
# Enums
# ============================================================================

class EventType(str, Enum):
    """Types of events - maps to specialized tables or generic events"""
    WORKOUT = "workout"
    MEAL = "meal"
    SLEEP = "sleep"
    COMMUTE = "commute"
    ENTERTAINMENT = "entertainment"
    COMMUNICATION = "communication"
    WORK = "work"
    REFLECTION = "reflection"
    GENERIC = "generic"  # Social visits, misc events


class EventCategory(str, Enum):
    """Event categories - semantic/contextual grouping"""
    HEALTH = "health"
    SOCIAL = "social"
    WORK = "work"
    TRAVEL = "travel"
    PERSONAL = "personal"
    FAMILY = "family"
    MEDIA = "media"
    EDUCATION = "education"
    MAINTENANCE = "maintenance"
    INTERACTION = "interaction"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class EventScope(str, Enum):
    """Event scope - single day, multi-day, trip, etc."""
    SINGLE_DAY = "single_day"
    MULTI_DAY = "multi_day"
    TRIP = "trip"
    VACATION = "vacation"
    PROJECT = "project"


class InformationSource(str, Enum):
    """How the user learned about an event"""
    DIRECT = "direct"  # User directly experienced/witnessed
    TOLD_BY_PERSON = "told_by_person"  # Someone told the user
    READ = "read"  # Read in book, article, etc.
    SOCIAL_MEDIA = "social_media"  # Saw on social media
    INFERRED = "inferred"  # User inferred/deduced
    CALL = "call"  # Learned during phone call
    TEXT = "text"  # Learned via text/messaging
    EMAIL = "email"  # Learned via email


class SourceConfidence(str, Enum):
    """Reliability/certainty of second-hand information"""
    CERTAIN = "certain"  # Highly confident
    PROBABLE = "probable"  # Likely true
    UNCERTAIN = "uncertain"  # Unsure/questionable


class CommunicationMedium(str, Enum):
    """Medium of communication"""
    AUDIO = "audio"  # Phone call, voice call
    VIDEO = "video"  # Video call (Zoom, FaceTime, etc.)
    IN_PERSON = "in_person"  # Face-to-face conversation
    EMAIL = "email"  # Email exchange
    TEXT = "text"  # Text message, SMS, chat
    VOICE_MESSAGE = "voice_message"  # Recorded voice message
    SOCIAL_MEDIA = "social_media"  # Social media DM, comment, post


class CommunicationType(str, Enum):
    """Type of communication interaction"""
    CALL = "call"  # Phone/voice call
    MEETING = "meeting"  # Scheduled meeting
    MESSAGE = "message"  # Asynchronous messaging
    CONVERSATION = "conversation"  # Casual conversation
    CONFERENCE = "conference"  # Group call/conference


class CommunicationPurpose(str, Enum):
    """Purpose of the communication"""
    SOCIAL = "social"  # Catching up, chatting
    WORK = "work"  # Work-related discussion
    PLANNING = "planning"  # Planning events/activities
    SUPPORT = "support"  # Emotional support, helping
    UPDATE = "update"  # Sharing updates/news
    PROBLEM_SOLVING = "problem_solving"  # Discussing/solving problems


class WorkoutCategory(str, Enum):
    STRENGTH = "STRENGTH"
    CARDIO = "CARDIO"
    MIXED = "MIXED"
    SPORTS = "SPORTS"
    FLEXIBILITY = "FLEXIBILITY"


class ExerciseCategory(str, Enum):
    STRENGTH = "strength"
    CARDIO = "cardio"
    FLEXIBILITY = "flexibility"
    SPORTS = "sports"
    PLYOMETRIC = "plyometric"


class SetType(str, Enum):
    WORKING = "WORKING"
    WARMUP = "WARMUP"
    DROP = "DROP"
    FAILURE = "FAILURE"


class MealTitle(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class MealType(str, Enum):
    HOME_COOKED = "home_cooked"
    RESTAURANT = "restaurant"
    TAKEOUT = "takeout"
    DELIVERED = "delivered"
    MEAL_PREP = "meal_prep"


class PortionSize(str, Enum):
    LIGHT = "light"
    REGULAR = "regular"
    HEAVY = "heavy"


class MealContext(str, Enum):
    POST_WORKOUT = "post_workout"
    PRE_WORKOUT = "pre_workout"
    SOCIAL = "social"
    BUSINESS = "business"
    ROUTINE = "routine"


# ============================================================================
# Health Tracking Enums
# ============================================================================

class HealthConditionType(str, Enum):
    """Type of health condition"""
    ILLNESS = "illness"
    INJURY = "injury"


class HealthConditionSeverity(str, Enum):
    """Severity level of health condition"""
    HOSPITALIZED = "hospitalized"      # Hospitalization required
    CLINIC_VISIT = "clinic_visit"      # Medical clinic/urgent care visit
    DOC_CONSULTATION = "doc_consultation"  # Doctor consultation
    HOME_REMEDY = "home_remedy"        # Home treatment
    MILD = "mild"                      # Mild symptoms
    MODERATE = "moderate"              # Moderate symptoms
    SEVERE = "severe"                  # Severe symptoms (non-hospitalized)


class WorkCategory(str, Enum):
    COMPANY = "company"
    PERSONAL = "personal"
    FREELANCE = "freelance"
    LEARNING = "learning"


class WorkType(str, Enum):
    FOCUSED_WORK = "focused_work"
    MEETING = "meeting"
    ADMIN = "admin"
    CREATIVE = "creative"
    PLANNING = "planning"


class Productivity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SleepQuality(str, Enum):
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"


class Significance(str, Enum):
    ROUTINE = "routine"
    NOTABLE = "notable"
    MAJOR = "major"
    MILESTONE = "milestone"
    MAJOR_MILESTONE = "major_milestone"


class TransportMode(str, Enum):
    """Transportation modes for commutes"""
    DRIVING = "driving"
    PUBLIC_TRANSIT = "public_transit"
    WALKING = "walking"
    CYCLING = "cycling"
    RUNNING = "running"
    FLYING = "flying"
    RIDESHARE = "rideshare"
    TAXI = "taxi"
    TRAIN = "train"
    BUS = "bus"
    SUBWAY = "subway"
    FERRY = "ferry"
    SCOOTER = "scooter"
    OTHER = "other"


class TrafficConditions(str, Enum):
    """Traffic conditions"""
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    CLEAR = "clear"


class EntertainmentType(str, Enum):
    """Types of entertainment"""
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    LIVE_PERFORMANCE = "live_performance"
    GAMING = "gaming"
    READING = "reading"
    STREAMING = "streaming"


class PerformanceType(str, Enum):
    """Types of live performances"""
    CONCERT = "concert"
    STANDUP_COMEDY = "standup_comedy"
    THEATRE = "theatre"
    MUSICAL = "musical"
    OPERA = "opera"
    BALLET = "ballet"
    SPORTS_EVENT = "sports_event"
    FESTIVAL = "festival"


class CompletionStatus(str, Enum):
    """Completion status for entertainment"""
    STARTED = "started"
    FINISHED = "finished"
    ABANDONED = "abandoned"
    IN_PROGRESS = "in_progress"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


# ============================================================================
# Base Models
# ============================================================================

class BaseEntity(BaseModel):
    """Base model for all entities"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Reference Data Models
# ============================================================================

class Person(BaseEntity):
    """Person entity"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    aliases: List[str] = Field(default_factory=list)
    relationship: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    kinship_to_owner: Optional[str] = Field(None, max_length=50)
    
    # Biographical info
    birthday: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    death_date: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    ethnicity: Optional[str] = Field(None, max_length=100)
    origin_location: Optional[str] = Field(None, max_length=255)
    known_since: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    last_interaction_date: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    
    # Google People API integration
    google_people_id: Optional[str] = Field(None, max_length=255, description="Google People API resource ID (e.g., 'people/c1234567890')")

    @field_validator('birthday', 'death_date', 'known_since', 'last_interaction_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        # Accept YYYY, YYYY-MM, or YYYY-MM-DD
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")


class PersonCreate(BaseModel):
    """Create person request"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    aliases: List[str] = Field(default_factory=list)
    relationship: Optional[str] = None
    category: Optional[str] = None
    kinship_to_owner: Optional[str] = Field(None, max_length=50)
    birthday: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    death_date: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    known_since: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    last_interaction_date: Optional[str] = Field(None, max_length=10, description="Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD")
    google_people_id: Optional[str] = Field(None, max_length=255, description="Google People API resource ID (e.g., 'people/c1234567890')")
    @field_validator('birthday', 'death_date', 'known_since', 'last_interaction_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")


class Location(BaseEntity):
    """Location entity"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    location_type: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    
    coordinates_lat: Optional[float] = None
    coordinates_lng: Optional[float] = None
    place_id: Optional[str] = Field(None, max_length=255)
    
    is_workout_location: bool = False
    equipment_available: List[str] = Field(default_factory=list)
    workout_types_supported: List[str] = Field(default_factory=list)
    
    notes: Optional[str] = None


class LocationCreate(BaseModel):
    """Create location request"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = None
    location_type: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    coordinates_lat: Optional[float] = None
    coordinates_lng: Optional[float] = None
    place_id: Optional[str] = None
    is_workout_location: bool = False
    equipment_available: List[str] = Field(default_factory=list)
    workout_types_supported: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class Exercise(BaseEntity):
    """Exercise catalog entry"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    category: ExerciseCategory
    family: Optional[str] = Field(None, max_length=50)
    
    primary_muscle_group: Optional[str] = Field(None, max_length=50)
    secondary_muscle_groups: List[str] = Field(default_factory=list)
    
    equipment: List[str] = Field(default_factory=list)
    variants: List[str] = Field(default_factory=list)
    
    difficulty: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class ExerciseCreate(BaseModel):
    """Create exercise request"""
    canonical_name: str = Field(..., min_length=1, max_length=255)
    category: ExerciseCategory
    family: Optional[str] = None
    primary_muscle_group: Optional[str] = None
    secondary_muscle_groups: List[str] = Field(default_factory=list)
    equipment: List[str] = Field(default_factory=list)
    variants: List[str] = Field(default_factory=list)
    difficulty: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# Event Models (Primary Aggregate Root)
# ============================================================================

class EventParticipant(BaseModel):
    """Participant in an event"""
    person_id: UUID
    person_name: Optional[str] = None  # Denormalized for convenience
    role: Optional[str] = None  # trainer, partner, friend, coach, etc.
    interaction_mode: Optional[str] = None  # in_person, virtual_video, virtual_audio, text_async, other


class Event(BaseEntity):
    """Event entity - primary aggregate root"""
    event_type: EventType
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    
    # Temporal (WHEN)
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    # event_date is now derived from start_time: DATE(start_time)
    
    # Location (WHERE)
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None  # Denormalized
    
    # Participants (WHO)
    participants: List[EventParticipant] = Field(default_factory=list)
    
    # Metadata
    category: Optional[str] = Field(None, max_length=100)
    significance: Significance = Significance.ROUTINE
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class EventCreate(BaseModel):
    """Create event request"""
    event_type: EventType
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location_id: Optional[UUID] = None
    parent_event_id: Optional[UUID] = None
    source_person_id: Optional[UUID] = None  # Person who provided secondhand info
    participants: List[EventParticipant] = Field(default_factory=list)
    category: Optional[str] = None
    significance: Significance = Significance.ROUTINE
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    # External system references (e.g., Garmin, Apple Health, Fitbit)
    external_event_id: Optional[str] = None
    external_event_source: Optional[str] = None


# ============================================================================
# Workout Models (Event Specialization)
# ============================================================================

class ExerciseSet(BaseModel):
    """Exercise set data"""
    id: UUID = Field(default_factory=uuid4)
    set_number: int = Field(..., ge=1)
    set_type: SetType = SetType.WORKING
    
    weight_kg: Optional[float] = Field(None, ge=0)
    reps: Optional[int] = Field(None, ge=0)
    duration_s: Optional[int] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    rest_time_s: Optional[int] = Field(None, ge=0)
    pace: Optional[str] = Field(None, max_length=50)
    
    # Interval training fields (for Tabata, HIIT, time-based workouts, etc.)
    interval_description: Optional[str] = None  # e.g., "20s work, 10s rest"
    work_duration_s: Optional[int] = Field(None, ge=0)
    rest_duration_s: Optional[int] = Field(None, ge=0)
    
    notes: Optional[str] = None


class WorkoutExercise(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    """Workout exercise with sets"""
    id: UUID = Field(default_factory=uuid4)
    exercise_id: UUID
    exercise_name: Optional[str] = None  # Denormalized for convenience
    sequence_order: int = Field(..., ge=1)
    sets: List[ExerciseSet] = Field(default_factory=list)
    rest_between_exercises_s: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None


class WorkoutSubtype(str, Enum):
    """Workout subtypes for polymorphic behavior"""
    GYM_STRENGTH = "GYM_STRENGTH"       # Traditional weightlifting
    GYM_CARDIO = "GYM_CARDIO"           # Treadmill, elliptical, stair climber
    RUN = "RUN"                         # Running (outdoor/indoor)
    SWIM = "SWIM"                       # Swimming
    BIKE = "BIKE"                       # Cycling (outdoor/indoor)
    HIKE = "HIKE"                       # Hiking/trekking
    SPORT = "SPORT"                     # Basketball, tennis, soccer, etc.
    YOGA = "YOGA"                       # Yoga sessions
    CROSSFIT = "CROSSFIT"               # CrossFit WODs
    CALISTHENICS = "CALISTHENICS"       # Bodyweight training
    DANCE = "DANCE"                     # Dance classes
    MARTIAL_ARTS = "MARTIAL_ARTS"       # Martial arts training
    OTHER = "OTHER"                     # Other workout types

    @classmethod
    def _missing_(cls, value):
        """Allow case-insensitive parsing (DB stores lowercase enum values)."""
        if isinstance(value, str):
            candidate = value.strip().upper()
            if candidate:
                for member in cls:
                    if member.value == candidate:
                        return member
        return None


class Workout(BaseEntity):
    """Workout entity - references an event"""
    event_id: UUID  # References parent event
    
    # Workout-specific fields
    workout_name: Optional[str] = Field(None, max_length=255)
    category: WorkoutCategory
    workout_subtype: Optional[WorkoutSubtype] = None  # Polymorphic type
    intensity: Optional[int] = Field(None, ge=1, le=10)  # 1-10 scale
    
    # Workout structure (mainly for gym workouts)
    exercises: List[WorkoutExercise] = Field(default_factory=list)
    warmup_duration_s: Optional[int] = Field(None, ge=0)
    cooldown_duration_s: Optional[int] = Field(None, ge=0)
    
    # Cardio-specific fields (RUN, SWIM, BIKE, HIKE)
    distance_km: Optional[float] = Field(None, ge=0)
    pace: Optional[str] = Field(None, max_length=50)
    elevation_gain_m: Optional[int] = Field(None, ge=0)
    route: Optional[str] = None
    avg_heart_rate: Optional[int] = Field(None, ge=0, le=300)
    max_heart_rate: Optional[int] = Field(None, ge=0, le=300)
    
    # Sport-specific fields (SPORT subtype)
    sport_type: Optional[str] = Field(None, max_length=100)  # 'basketball', 'tennis', etc.
    game_type: Optional[str] = Field(None, max_length=50)    # 'pickup', 'league', etc.
    score: Optional[str] = None                              # '21-18' or 'Won 3-2'
    
    # Computed fields (updated via triggers)
    total_exercises: int = 0
    total_sets: int = 0
    total_volume_kg: float = 0.0
    
    def model_post_init(self, __context):
        """Calculate computed fields after initialization"""
        super().model_post_init(__context)
        if self.exercises:
            self.total_exercises = len(self.exercises)
            self.total_sets = sum(len(ex.sets) for ex in self.exercises)
            self.total_volume_kg = sum(
                set_data.weight_kg * set_data.reps
                for ex in self.exercises
                for set_data in ex.sets
                if set_data.weight_kg and set_data.reps
            )


class WorkoutCreate(BaseModel):
    """Create workout request"""
    workout_name: Optional[str] = None
    category: WorkoutCategory
    workout_subtype: Optional[WorkoutSubtype] = None
    intensity: Optional[int] = Field(None, ge=1, le=10)
    
    # Gym workout fields
    exercises: List[WorkoutExercise] = Field(default_factory=list)
    warmup_duration_s: Optional[int] = None
    cooldown_duration_s: Optional[int] = None
    
    # Cardio fields
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[int] = None
    route: Optional[str] = None
    
    # Sport fields
    sport_type: Optional[str] = None
    game_type: Optional[str] = None
    score: Optional[str] = None


class WorkoutWithEvent(BaseModel):
    """Complete workout with event data"""
    event: Event
    workout: Workout


# ============================================================================
# Meal Models (Event Specialization)
# ============================================================================

class MealItem(BaseModel):
    """Meal food item (nutrition tracking removed - out of scope for journal)"""
    id: UUID = Field(default_factory=uuid4)
    item_name: str = Field(..., min_length=1, max_length=255)
    quantity: Optional[str] = Field(None, max_length=100)


class MealItemCreate(BaseModel):
    """Meal item create model (for adding items to existing meals)"""
    meal_id: UUID  # ID of meal this item belongs to
    item_name: str = Field(..., min_length=1, max_length=255)
    quantity: Optional[str] = Field(None, max_length=100)


class Meal(BaseEntity):
    """Meal entity - references an event"""
    event_id: UUID  # References parent event
    
    # Meal-specific fields
    meal_name: Optional[str] = Field(None, max_length=255)
    meal_title: Optional[MealTitle] = None
    meal_type: Optional[MealType] = None
    portion_size: Optional[PortionSize] = None
    context: Optional[MealContext] = None
    
    # Food items
    items: List[MealItem] = Field(default_factory=list)
    
    # Aggregated nutrition
    total_calories: Optional[float] = Field(None, ge=0)
    total_protein_g: Optional[float] = Field(None, ge=0)
    total_carbs_g: Optional[float] = Field(None, ge=0)
    total_fats_g: Optional[float] = Field(None, ge=0)


class MealCreate(BaseModel):
    """Create meal request"""
    meal_name: Optional[str] = None
    meal_title: Optional[MealTitle] = None
    meal_type: Optional[MealType] = None
    portion_size: Optional[PortionSize] = None
    context: Optional[MealContext] = None
    items: List[MealItem] = Field(default_factory=list)
    total_calories: Optional[float] = None
    total_protein_g: Optional[float] = None
    total_carbs_g: Optional[float] = None
    total_fats_g: Optional[float] = None


class MealWithEvent(BaseModel):
    """Complete meal with event data"""
    event: Event
    meal: Meal


# ============================================================================
# Reflection Models (Event Specialization)
# ============================================================================

class Reflection(BaseEntity):
    """Reflection entity - references an event"""
    event_id: UUID  # References parent event
    
    # Reflection specifics
    reflection_type: Optional[str] = None  # daily, weekly, gratitude, learning, goal_review, decision, other
    mood: Optional[str] = None  # positive, negative, neutral, mixed, anxious, excited, sad, grateful, etc.
    mood_score: Optional[int] = None  # 1-10 emotional state
    
    # Structured reflection prompts
    prompt_question: Optional[str] = None
    key_insights: Optional[List[str]] = None
    action_items: Optional[List[str]] = None


class ReflectionCreate(BaseModel):
    """Create reflection request"""
    event_id: UUID
    reflection_type: Optional[str] = None
    mood: Optional[str] = None
    mood_score: Optional[int] = None
    prompt_question: Optional[str] = None
    key_insights: Optional[List[str]] = None
    action_items: Optional[List[str]] = None


# ============================================================================
# Commute Models (Event Specialization)
# ============================================================================

class Commute(BaseEntity):
    """Commute/travel entity - references an event"""
    event_id: UUID  # References parent event
    
    # Travel specifics
    from_location_id: Optional[UUID] = None
    to_location_id: Optional[UUID] = None
    
    # Transport details
    transport_mode: TransportMode
    transport_subtype: Optional[str] = Field(None, max_length=50)
    
    # Metrics
    distance_km: Optional[float] = Field(None, ge=0)
    travel_time_minutes: Optional[int] = Field(None, ge=0)
    
    # Cost and conditions
    cost: Optional[float] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=10)
    traffic_conditions: Optional[TrafficConditions] = None
    delays_minutes: int = Field(default=0, ge=0)
    
    # Additional context
    purpose: Optional[str] = Field(None, max_length=100)
    route_taken: Optional[str] = None
    parking_info: Optional[str] = None


class CommuteCreate(BaseModel):
    """Create commute request"""
    from_location_id: Optional[UUID] = None
    to_location_id: Optional[UUID] = None
    transport_mode: TransportMode
    transport_subtype: Optional[str] = None
    distance_km: Optional[float] = None
    travel_time_minutes: Optional[int] = None
    cost: Optional[float] = None
    currency: str = "USD"
    traffic_conditions: Optional[TrafficConditions] = None
    delays_minutes: int = 0
    purpose: Optional[str] = None
    route_taken: Optional[str] = None
    parking_info: Optional[str] = None


class CommuteWithEvent(BaseModel):
    """Complete commute with event data"""
    event: Event
    commute: Commute


# ============================================================================
# Entertainment Models (Event Specialization)
# ============================================================================

class Entertainment(BaseEntity):
    """Entertainment entity - references an event"""
    event_id: UUID  # References parent event
    
    # Classification
    entertainment_type: EntertainmentType
    title: str = Field(..., max_length=500)
    
    # Creators/Attribution
    creator: Optional[str] = Field(None, max_length=255)
    genre: Optional[str] = Field(None, max_length=100)
    
    # TV Show specifics
    show_name: Optional[str] = Field(None, max_length=255)
    season_number: Optional[int] = Field(None, ge=1)
    episode_number: Optional[int] = Field(None, ge=1)
    episode_title: Optional[str] = Field(None, max_length=255)
    
    # YouTube/Podcast specifics
    channel_name: Optional[str] = Field(None, max_length=255)
    video_url: Optional[str] = None
    
    # Movie specifics
    director: Optional[str] = Field(None, max_length=255)
    release_year: Optional[int] = Field(None, ge=1800, le=2100)
    
    # Live Performance specifics
    performance_type: Optional[PerformanceType] = None
    venue: Optional[str] = Field(None, max_length=255)
    performer_artist: Optional[str] = Field(None, max_length=255)
    
    # Gaming specifics
    game_platform: Optional[str] = Field(None, max_length=100)
    game_genre: Optional[str] = Field(None, max_length=100)
    
    # Platform and format
    platform: Optional[str] = Field(None, max_length=100)
    format: Optional[str] = Field(None, max_length=50)
    
    # User feedback
    personal_rating: Optional[int] = Field(None, ge=1, le=10)
    completion_status: CompletionStatus = Field(default=CompletionStatus.FINISHED)
    rewatch: bool = False
    
    # Social context
    watched_with_others: bool = False


class EntertainmentCreate(BaseModel):
    """Create entertainment request"""
    entertainment_type: EntertainmentType
    title: str
    creator: Optional[str] = None
    genre: Optional[str] = None
    show_name: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    episode_title: Optional[str] = None
    channel_name: Optional[str] = None
    video_url: Optional[str] = None
    director: Optional[str] = None
    release_year: Optional[int] = None
    performance_type: Optional[PerformanceType] = None
    venue: Optional[str] = None
    performer_artist: Optional[str] = None
    game_platform: Optional[str] = None
    game_genre: Optional[str] = None
    platform: Optional[str] = None
    format: Optional[str] = None
    personal_rating: Optional[int] = Field(None, ge=1, le=10)
    completion_status: CompletionStatus = CompletionStatus.FINISHED
    rewatch: bool = False
    watched_with_others: bool = False


class EntertainmentWithEvent(BaseModel):
    """Complete entertainment with event data"""
    event: Event
    entertainment: Entertainment


# ============================================================================
# Sleep Models (Event Specialization)
# ============================================================================

class SleepSession(BaseEntity):
    """Sleep session - references an event"""
    event_id: UUID  # References parent event
    
    # Sleep-specific fields
    quality: Optional[SleepQuality] = None
    interruptions: int = Field(default=0, ge=0)
    dream_recall: bool = False


class SleepSessionCreate(BaseModel):
    """Create sleep session request"""
    quality: Optional[SleepQuality] = None
    interruptions: int = 0
    dream_recall: bool = False


class SleepWithEvent(BaseModel):
    """Complete sleep session with event data"""
    event: Event
    sleep_session: SleepSession


# ============================================================================
# Reflection Models (Event Specialization)
# ============================================================================
# Reflection Models (Event Specialization) - moved to earlier in file
# See lines ~675 for the event-centric Reflection model
# ============================================================================

# NOTE: Reflection model is defined in the Reflection Models section (event-centric architecture)
# The old standalone reflection model has been removed in favor of event-based reflections


# NOTE: ReflectionCreate is defined in the Reflection Models section (event-centric architecture)
# The old standalone reflection model has been removed in favor of event-based reflections


class ReflectionWithEvent(BaseModel):
    """Complete reflection with event data"""
    event: Event
    reflection: Reflection


# ============================================================================
# Work Models (kept separate - not event-based currently)
# ============================================================================

class WorkBlock(BaseModel):
    """Work block within a work day"""
    id: UUID = Field(default_factory=uuid4)
    start_time: datetime
    end_time: datetime
    duration_minutes: Optional[int] = None
    
    location: Optional[str] = Field(None, max_length=50)
    category: WorkCategory
    work_type: WorkType
    productivity: Optional[Productivity] = None
    
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class WorkDay(BaseEntity):
    """Work day summary"""
    work_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    total_time_minutes: int = 0
    primary_location: Optional[str] = Field(None, max_length=50)
    blocks: List[WorkBlock] = Field(default_factory=list)
    notes: Optional[str] = None


class WorkDayCreate(BaseModel):
    """Create work day request"""
    work_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    primary_location: Optional[str] = None
    blocks: List[WorkBlock] = Field(default_factory=list)
    notes: Optional[str] = None


# ============================================================================
# Raw Journal Entry Models
# ============================================================================

class JournalEntry(BaseEntity):
    """Raw journal entry - preserves original user input"""
    raw_text: str = Field(..., min_length=1)
    entry_timestamp: Optional[datetime] = None
    entry_date: Union[str, date]  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    
    # Input metadata
    input_method: str = Field(default="text", max_length=50)
    word_count: Optional[int] = Field(None, ge=0)
    character_count: Optional[int] = Field(None, ge=0)
    
    # Processing metadata
    processed: bool = False
    processing_notes: Optional[str] = None
    
    # Context
    entry_type: str = Field(default="journal", max_length=50)  # journal, quick_log, reflection, import
    tags: List[str] = Field(default_factory=list)


class JournalEntryCreate(BaseModel):
    """Create journal entry request"""
    raw_text: str = Field(..., min_length=1)
    entry_timestamp: Optional[datetime] = None  # Defaults to NOW() in DB
    entry_date: Optional[str] = None  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    input_method: str = "text"
    entry_type: str = "journal"
    tags: List[str] = Field(default_factory=list)
    processing_notes: Optional[str] = None

    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")


class JournalEntryEventLink(BaseModel):
    """Link between journal entry and extracted event"""
    journal_entry_id: UUID
    event_id: UUID
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    notes: Optional[str] = None


class JournalEntryWithEvents(BaseModel):
    """Journal entry with its extracted events"""
    entry: JournalEntry
    event_ids: List[UUID] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)


# ============================================================================
# Journal Day Models
# ============================================================================

class JournalDay(BaseEntity):
    """Daily summary aggregating all activities"""
    journal_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    
    day_title: Optional[str] = Field(None, max_length=255)
    day_rating: Optional[int] = Field(None, ge=1, le=10)
    highlights: List[str] = Field(default_factory=list)
    
    @field_validator('highlights', mode='before')
    @classmethod
    def ensure_highlights_is_list(cls, v):
        """Ensure highlights is always a list, even if None from database"""
        if v is None:
            return []
        return v
    
    # Quick stats
    workout_count: int = 0
    meal_count: int = 0
    commute_count: int = 0
    entertainment_count: int = 0
    event_count: int = 0
    reflection_count: int = 0
    work_minutes: int = 0
    sleep_hours: Optional[float] = None
    total_commute_minutes: int = 0
    journal_entry_count: int = 0
    
    notes: Optional[str] = None


class JournalDayCreate(BaseModel):
    """Create journal day request"""
    journal_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    day_title: Optional[str] = None
    day_rating: Optional[int] = Field(None, ge=1, le=10)
    highlights: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


# ============================================================================
# Health Tracking Models
# ============================================================================

class HealthCondition(BaseEntity):
    """Health condition (illness or injury) - event-based"""
    event_id: UUID
    person_id: Optional[UUID] = None  # Direct person reference for easy querying

    condition_type: HealthConditionType
    condition_name: str = Field(..., max_length=255)
    severity: Optional[HealthConditionSeverity] = None
    severity_score: Optional[int] = Field(None, ge=1, le=10)

    is_sport_related: bool = False
    sport_type: Optional[str] = Field(None, max_length=100)

    start_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    end_date: Optional[str] = None  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD

    notes: Optional[str] = None
    
    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def convert_date_to_string(cls, v):
        """Convert date objects from DB to ISO string format"""
        if v is None:
            return v
        if hasattr(v, 'isoformat'):  # It's a date/datetime object
            return v.isoformat()
        return v


class HealthConditionCreate(BaseModel):
    """Create health condition request"""
    event_id: UUID
    person_id: Optional[UUID] = None  # Optional person reference (defaults to owner if not provided)

    condition_type: HealthConditionType
    condition_name: str = Field(..., max_length=255)
    severity: Optional[HealthConditionSeverity] = None
    severity_score: Optional[int] = Field(None, ge=1, le=10)

    is_sport_related: bool = False
    sport_type: Optional[str] = None

    start_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    end_date: Optional[str] = None  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")

    notes: Optional[str] = None


class HealthConditionWithEvent(BaseModel):
    """Health condition with its associated event"""
    event: Event
    condition: HealthCondition


class HealthConditionLog(BaseEntity):
    """Health condition progression log entry — one per condition per day"""
    condition_id: UUID
    person_id: Optional[UUID] = None  # Inherited from parent condition for easy querying
    log_date: str  # YYYY-MM-DD
    severity: Optional[HealthConditionSeverity] = None
    severity_score: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None

    @field_validator('log_date', mode='before')
    @classmethod
    def convert_date_to_string(cls, v):
        if v is None:
            return v
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return v


class HealthConditionLogCreate(BaseModel):
    """Create health condition log entry"""
    condition_id: UUID
    person_id: Optional[UUID] = None  # Inherited from parent condition (auto-filled if not provided)
    log_date: str  # YYYY-MM-DD
    severity: Optional[HealthConditionSeverity] = None
    severity_score: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None


class HealthMedicine(BaseEntity):
    """Medicine taken - optionally linked to health condition or event"""
    event_id: Optional[UUID] = None
    condition_id: Optional[UUID] = None
    
    medicine_name: str = Field(..., max_length=255)
    dosage: Optional[str] = Field(None, max_length=100)
    dosage_unit: Optional[str] = Field(None, max_length=50)
    frequency: Optional[str] = Field(None, max_length=100)
    
    log_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    log_time: Optional[time] = None
    
    notes: Optional[str] = None
    
    @field_validator('log_date', mode='before')
    @classmethod
    def convert_date_to_string(cls, v):
        """Convert date objects from DB to ISO string format"""
        if v is None:
            return v
        if hasattr(v, 'isoformat'):  # It's a date/datetime object
            return v.isoformat()
        return v


class HealthMedicineCreate(BaseModel):
    """Create health medicine request"""
    event_id: Optional[UUID] = None
    condition_id: Optional[UUID] = None
    
    medicine_name: str = Field(..., max_length=255)
    dosage: Optional[str] = None
    dosage_unit: Optional[str] = None
    frequency: Optional[str] = None
    
    log_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD

    @field_validator('log_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")
    log_time: Optional[time] = None
    
    notes: Optional[str] = None


class HealthSupplement(BaseEntity):
    """Dietary supplement - wellness logging"""
    event_id: Optional[UUID] = None
    
    supplement_name: str = Field(..., max_length=255)
    amount: Optional[str] = Field(None, max_length=100)
    amount_unit: Optional[str] = Field(None, max_length=50)
    frequency: Optional[str] = Field(None, max_length=100)
    
    log_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    log_time: Optional[time] = None
    
    notes: Optional[str] = None
    
    @field_validator('log_date', mode='before')
    @classmethod
    def convert_date_to_string(cls, v):
        """Convert date objects from DB to ISO string format"""
        if v is None:
            return v
        if hasattr(v, 'isoformat'):  # It's a date/datetime object
            return v.isoformat()
        return v


class HealthSupplementCreate(BaseModel):
    """Create health supplement request"""
    event_id: Optional[UUID] = None
    
    supplement_name: str = Field(..., max_length=255)
    amount: Optional[str] = None
    amount_unit: Optional[str] = None
    frequency: Optional[str] = None
    
    log_date: str  # Partial date string: YYYY, YYYY-MM, or YYYY-MM-DD

    @field_validator('log_date', mode='before')
    @classmethod
    def validate_partial_date(cls, v, info):
        if v is None:
            return v
        import re
        if re.fullmatch(r"\d{4}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        raise ValueError(f"Invalid date format for {info.field_name}: '{v}'. Must be YYYY, YYYY-MM, or YYYY-MM-DD.")
    log_time: Optional[time] = None
    
    notes: Optional[str] = None
