// M5 Runtime core type definitions
// Per M5_runtime.md §3.2 and §5.3

// --- Board Actions ---
export type BoardAction =
  | 'write_title'
  | 'write_subtitle'
  | 'write_bullets'
  | 'write_steps'
  | 'write_summary'
  | 'clear_board'
  | 'highlight';

// --- Timeline Item discriminated union (6 types) ---
export interface SpeakItem {
  seq: number;
  type: 'speak';
  event_id: string;
  text: string;
  audio_path: string;
  duration_sec: number;
  start_offset_sec: number;
}

export interface BoardItem {
  seq: number;
  type: 'board';
  event_id: string;
  action: BoardAction;
  content: string | string[];
  dwell_sec: number;
  start_offset_sec: number;
}

export interface FormulaItem {
  seq: number;
  type: 'formula';
  event_id: string;
  latex: string;
  display_mode: 'block' | 'inline';
  dwell_sec?: number;
  start_offset_sec: number;
}

export interface TableItem {
  seq: number;
  type: 'table';
  event_id: string;
  title: string;
  columns: string[];
  rows: string[][];
  dwell_sec?: number;
  start_offset_sec: number;
}

export interface ImageItem {
  seq: number;
  type: 'image';
  event_id: string;
  src: string;
  caption: string;
  media_type: 'static' | 'gif';
  image_id?: string;
  dwell_sec?: number;
  start_offset_sec: number;
}

export interface PauseItem {
  seq: number;
  type: 'pause';
  event_id: string;
  duration_sec: number;
  start_offset_sec: number;
}

export interface QuizItem {
  seq: number;
  type: 'quiz';
  event_id: string;
  question: string;
  options: string[];
  blocking: boolean;
  start_offset_sec: number;
}

export type TimelineItem =
  | SpeakItem
  | BoardItem
  | FormulaItem
  | TableItem
  | ImageItem
  | PauseItem
  | QuizItem;

// --- PlaybackData ---
export interface PlaybackData {
  session_id: string;
  turn: number;
  teacher_id: string;
  skill_id?: string;
  avatar?: {
    pixel_url?: string;
    live2d_model_id?: string;
  };
  voice_id: string;
  timeline: TimelineItem[];
  total_duration_sec: number;
  generated_at?: string;
}

// --- Player Events ---
export type PlayerEventName =
  | 'timeline:item'
  | 'audio:start'
  | 'audio:end'
  | 'play'
  | 'pause'
  | 'seek'
  | 'speedchange'
  | 'end'
  | 'error'
  | 'waiting'   // 流式 push 模式：事件缓冲耗尽，等上游推送更多
  | 'resumed';  // 新事件到达，从 waiting 恢复播放

export interface PlayerEvent {
  type: PlayerEventName;
  data?: any;
}

export type PlayerEventHandler = (event: PlayerEvent) => void;

// --- PlayerRuntime interface ---
export interface PlayerRuntime {
  load(playback: PlaybackData): Promise<void>;
  play(): void;
  pause(): void;
  seek(seq: number): void;
  setSpeed(rate: number): void;
  on(event: PlayerEventName, cb: PlayerEventHandler): void;
  destroy(): void;
}

// --- Board State ---
export interface BoardStateItem {
  eventId: string;
  action: BoardAction | 'formula' | 'table' | 'image';
  content: any;
  highlighted: boolean;
  timestamp: number;
}

// --- Avatar Descriptor ---
export interface AvatarDescriptor {
  type: 'live2d' | 'stub' | 'pixel';
  ready: boolean;
  modelPath?: string;
}

// Valid event types for validation
export const VALID_EVENT_TYPES = new Set([
  'speak', 'board', 'formula', 'table', 'image', 'pause', 'quiz',
]);

// Valid speed rates
export const VALID_SPEEDS = new Set([0.75, 1.0, 1.25, 1.5]);
