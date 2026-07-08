import type { AvatarDescriptor } from '../player_runtime/types';

// Stub avatar loader — no Live2D SDK available yet
export class AvatarLoader {
  async load(_modelId: string): Promise<AvatarDescriptor> {
    console.warn(`[AvatarLoader] Live2D model "${_modelId}" not available — using stub`);
    return { type: 'stub', ready: true };
  }
}
