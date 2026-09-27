export interface TrackPoint {
  t: number;
  x: number;
  y: number;
  w: number;
  h: number;
  speed: number;
  heading: number;
}

export interface SceneObject {
  id: string;
  kind: string;
  category: string;
  trajectory: TrackPoint[];
  keyframes: number[];
  confidence: number;
}

export interface SceneEvent {
  type: string;
  t: number;
  objects: string[];
  impact_speed?: number;
  confidence: number;
}

export interface SceneItem {
  scene_id: string;
  objects: SceneObject[];
  events: SceneEvent[];
  confidence: number;
  low_confidence: boolean;
}

export interface Party {
  object_id: string;
  role: string;
  liability_pct: number;
  main_reason: string;
}

export interface Judgment {
  case_type?: string;
  parties: Party[];
  reasoning: string[];
  laws: { article: string; summary: string }[];
  confidence: number;
  low_confidence: boolean;
}

export interface Action {
  order: number;
  action: string;
  urgent: boolean;
  checked: boolean;
}

export interface ResponsePlan {
  emergency_level: string;
  level_label: string;
  urgent_actions: Action[];
  steps: Action[];
  insurance_note: string;
  confidence: number;
}
