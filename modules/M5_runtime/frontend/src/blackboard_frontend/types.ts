import type { BoardAction } from '../player_runtime/types';

export interface BoardStateItem {
  eventId: string;
  action: BoardAction | 'formula' | 'table' | 'image';
  content: any;
  highlighted: boolean;
  timestamp: number;
  // 聚焦分组：同一段连续写出的板书共享一个 groupId；中间讲过话(speak)后再写的板书属于新组。
  // 「当前活跃组」(App 里的 activeGroupId)放大显示，旧组平滑缩回正常字号。回看静态模式不带此字段。
  groupId?: number;
}

export type ActionHandler = (
  state: Map<string, BoardStateItem>,
  item: BoardStateItem
) => Map<string, BoardStateItem>;
