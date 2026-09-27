import './DataTable.css';

/**
 * DataTable — glass table with sticky header, hover rows, empty state.
 * columns: [{ key, label, width?, align?, render?(row) }]
 */
export default function DataTable({ columns, rows, onRowClick, emptyMessage = 'No records found', loading }) {
  if (loading) {
    return (
      <div className="dt-loading">
        <div className="spinner" />
        <span>Loading data…</span>
      </div>
    );
  }
  if (!rows || rows.length === 0) {
    return <div className="dt-empty">{emptyMessage}</div>;
  }

  return (
    <div className="dt-wrap">
      <table className="dt-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align || 'left' }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.id || row.assetID || row.txId || row.sampleId || i}
              className={onRowClick ? 'clickable' : ''}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align || 'left' }}>
                  {c.render ? c.render(row) : row[c.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
