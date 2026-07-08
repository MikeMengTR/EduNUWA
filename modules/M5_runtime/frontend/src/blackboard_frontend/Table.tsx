interface TableProps {
  title: string;
  columns: string[];
  rows: string[][];
}

export function Table({ title, columns, rows }: TableProps) {
  return (
    <div className="board-item board-table-container">
      <h3 className="board-table-title">{title}</h3>
      <table className="board-table">
        <thead>
          <tr>{columns.map((col, i) => <th key={i}>{col}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
