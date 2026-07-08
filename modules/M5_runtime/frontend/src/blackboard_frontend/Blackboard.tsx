// Blackboard main component — ACTION_HANDLERS dispatch map per M5_runtime.md §9.5
// H2 enforcement: Record<BoardAction, ActionHandler> ensures all 7 actions are handled
import { useRef, useEffect } from 'react';
import type { BoardAction } from '../player_runtime/types';
import type { BoardStateItem, ActionHandler } from './types';
import { WriteTitle } from './actions/WriteTitle';
import { WriteSubtitle } from './actions/WriteSubtitle';
import { WriteBullets } from './actions/WriteBullets';
import { WriteSteps } from './actions/WriteSteps';
import { WriteSummary } from './actions/WriteSummary';
import { Formula } from './Formula';
import { Table } from './Table';
import { BoardImage } from './BoardImage';
import { renderMathToHtml } from '../shared/renderMath';
import './Blackboard.css';

const ACTION_HANDLERS: Record<BoardAction, ActionHandler> = {
  write_title: (state, item) => {
    state.set(item.eventId, item);
    return state;
  },
  write_subtitle: (state, item) => {
    state.set(item.eventId, item);
    return state;
  },
  write_bullets: (state, item) => {
    state.set(item.eventId, item);
    return state;
  },
  write_steps: (state, item) => {
    state.set(item.eventId, item);
    return state;
  },
  write_summary: (state, item) => {
    state.set(item.eventId, item);
    return state;
  },
  clear_board: (state, _item) => {
    state.clear();
    return state;
  },
  highlight: (state, item) => {
    const existing = state.get(item.eventId);
    if (existing) {
      existing.highlighted = !existing.highlighted;
    }
    return state;
  },
};

function getActionComponent(action: BoardAction | 'formula' | 'table' | 'image'): React.ComponentType<any> | null {
  const map: Record<string, React.ComponentType<any>> = {
    write_title: WriteTitle,
    write_subtitle: WriteSubtitle,
    write_bullets: WriteBullets,
    write_steps: WriteSteps,
    write_summary: WriteSummary,
    clear_board: () => null,
    highlight: () => null,
    formula: FormulaWrapper,
    table: TableWrapper,
    image: ImageWrapper,
  };
  return map[action] || WriteBullets;  // 未知 action 回退为普通板书，避免内容丢失
}

function FormulaWrapper({ content }: { content: any }) {
  return <Formula latex={content.latex} displayMode={content.display_mode || 'block'} />;
}

function TableWrapper({ content }: { content: any }) {
  return <Table title={content.title} columns={content.columns} rows={content.rows} />;
}

function ImageWrapper({ content }: { content: any }) {
  return <BoardImage src={content.src} caption={content.caption} mediaType={content.media_type} />;
}

interface BlackboardProps {
  items: BoardStateItem[];
  currentText?: string;
  // 当前活跃板书组：该组板书放大聚焦，其余组正常字号。回看静态模式不传 → 全部正常。
  activeGroupId?: number;
}

export function Blackboard({ items, currentText, activeGroupId }: BlackboardProps) {
  const sorted = [...items].sort((a, b) => a.timestamp - b.timestamp);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 跟随最新内容：活跃组（最新板书）在底部，放大后可能超出可视区。仅当用户本就贴着底部
  // 时才平滑滚到底（near-bottom 粘附），避免用户上翻回看历史板书时被强行拽回。
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [sorted.length, activeGroupId, currentText]);

  return (
    <div className="blackboard" ref={scrollRef}>
      <div className="blackboard-surface">
        {sorted.map((item) => {
          const Comp = getActionComponent(item.action);
          if (!Comp) return null;
          const isFocus = item.groupId !== undefined && item.groupId === activeGroupId;
          const classes = [
            'board-item-wrapper',
            isFocus ? 'is-focus' : '',
            item.highlighted ? 'board-item--highlighted' : '',
          ].filter(Boolean).join(' ');

          return (
            <div key={item.eventId} className={classes}>
              <Comp content={item.content} />
            </div>
          );
        })}
        {currentText && (
          <div className="board-item-wrapper board-subtitle-text">
            {/* 字幕同样走 renderMath：AI 偶尔在口播文本里夹 **粗体** 或 $公式$，
                纯文本渲染会显示成原始符号 */}
            <p
              className="board-speak-text"
              dangerouslySetInnerHTML={{ __html: renderMathToHtml(currentText) }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// Utility to apply a board action to state
export function applyBoardAction(
  state: BoardStateItem[],
  item: BoardStateItem,
): BoardStateItem[] {
  const map = new Map(state.map(s => [s.eventId, { ...s }]));
  const handler = ACTION_HANDLERS[item.action as BoardAction];
  if (handler) {
    handler(map, item);
  } else {
    // 未知 action（AI 可能输出系统外的类型，如 write_definition）：回退为普通板书项，避免内容被丢弃
    map.set(item.eventId, item);
  }
  return Array.from(map.values());
}
