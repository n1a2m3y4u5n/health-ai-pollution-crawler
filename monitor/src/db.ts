import fs from 'fs';
import path from 'path';

// fly.io 볼륨 경로 또는 로컬 data/ 디렉토리
const DATA_DIR = process.env.DATA_DIR ?? path.join(__dirname, '..', 'data');
const DB_FILE = path.join(DATA_DIR, 'seen_posts.json');

interface SeenData {
  // boardId → 확인한 uid Set (JSON에서는 배열로 직렬화)
  [boardId: string]: string[];
}

function load(): SeenData {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(DB_FILE)) {
    return {};
  }
  try {
    return JSON.parse(fs.readFileSync(DB_FILE, 'utf-8')) as SeenData;
  } catch {
    return {};
  }
}

function save(data: SeenData): void {
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf-8');
}

export function getSeenUids(boardId: string): Set<string> {
  const data = load();
  return new Set(data[boardId] ?? []);
}

export function markSeen(boardId: string, uids: string[]): void {
  const data = load();
  const existing = new Set(data[boardId] ?? []);
  for (const uid of uids) existing.add(uid);
  data[boardId] = Array.from(existing);
  save(data);
}
