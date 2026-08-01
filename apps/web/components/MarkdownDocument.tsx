import type { ReactNode } from "react";

import { slugifyHeading } from "@/lib/documents";

type MarkdownDocumentProps = {
  content: string;
};

function renderInline(value: string, keyPrefix: string): ReactNode[] {
  return value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string | undefined): boolean {
  if (!line || !line.includes("|")) return false;
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index]?.trim() ?? "";
  return (
    /^#{1,6}\s+/.test(line) ||
    /^>\s?/.test(line) ||
    /^-\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    (line.includes("|") && isTableSeparator(lines[index + 1]))
  );
}

function renderHeading(depth: number, value: string, key: string): ReactNode {
  const id = slugifyHeading(value);
  const content = renderInline(value, key);
  if (depth === 1) return <h1 key={key} id={id}>{content}</h1>;
  if (depth === 2) return <h2 key={key} id={id}>{content}</h2>;
  if (depth === 3) return <h3 key={key} id={id}>{content}</h3>;
  if (depth === 4) return <h4 key={key} id={id}>{content}</h4>;
  if (depth === 5) return <h5 key={key} id={id}>{content}</h5>;
  return <h6 key={key} id={id}>{content}</h6>;
}

export function MarkdownDocument({ content }: MarkdownDocumentProps) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push(renderHeading(heading[1].length, heading[2], `heading-${index}`));
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      const start = index;
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(
        <blockquote key={`quote-${start}`}>
          <p>{renderInline(quote.join(" "), `quote-${start}`)}</p>
        </blockquote>,
      );
      continue;
    }

    if (line.includes("|") && isTableSeparator(lines[index + 1])) {
      const start = index;
      const headers = splitTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="document-table-wrap" key={`table-${start}`}>
          <table>
            <thead>
              <tr>{headers.map((cell, cellIndex) => <th key={`header-${cellIndex}`}>{renderInline(cell, `header-${cellIndex}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {headers.map((_, cellIndex) => (
                    <td key={`cell-${rowIndex}-${cellIndex}`}>
                      {renderInline(row[cellIndex] ?? "", `cell-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^-\s+/.test(line)) {
      const items: Array<{ checked?: boolean; content: string }> = [];
      const start = index;
      while (index < lines.length && /^-\s+/.test(lines[index].trim())) {
        const item = lines[index].trim().replace(/^-\s+/, "");
        const task = item.match(/^\[([ xX])\]\s*(.*)$/);
        items.push(task ? { checked: task[1].toLowerCase() === "x", content: task[2] } : { content: item });
        index += 1;
      }
      const hasTasks = items.some((item) => item.checked !== undefined);
      blocks.push(
        <ul className={hasTasks ? "task-list" : undefined} key={`list-${start}`}>
          {items.map((item, itemIndex) => (
            <li key={`item-${itemIndex}`}>
              {item.checked !== undefined && <input aria-label="Item do template" checked={item.checked} disabled readOnly type="checkbox" />}
              <span>{renderInline(item.content, `item-${start}-${itemIndex}`)}</span>
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      const start = index;
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={`ordered-list-${start}`}>
          {items.map((item, itemIndex) => <li key={`item-${itemIndex}`}>{renderInline(item, `ordered-${start}-${itemIndex}`)}</li>)}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [];
    const start = index;
    while (index < lines.length && lines[index].trim() && !startsBlock(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${start}`}>{renderInline(paragraph.join(" "), `paragraph-${start}`)}</p>);
  }

  return <div className="markdown-document">{blocks}</div>;
}
