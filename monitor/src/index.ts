import cron from 'node-cron';
import { scrapePosts } from './scraper';
import { sendNewPostsAlert, sendStartupAlert } from './mailer';
import { getSeenUids, markSeen } from './db';

interface Board {
  id: string;
  name: string;
  url: string;
}

const BOARDS: Board[] = [
  {
    id: 'notice',
    name: '공지사항',
    url: 'https://e-icon.or.kr/ko/%EA%B3%B5%EC%A7%80%EC%82%AC%ED%95%AD/',
  },
  {
    id: 'qa',
    name: 'Q&A',
    url: 'https://e-icon.or.kr/ko/qa/',
  },
];

async function checkBoard(board: Board): Promise<void> {
  console.log(`[${new Date().toISOString()}] 확인 중 — ${board.name}`);

  const posts = await scrapePosts(board.url);
  if (posts.length === 0) {
    console.log(`  → 게시글 없음 (파싱 실패 가능성)`);
    return;
  }

  const seenUids = getSeenUids(board.id);
  const newPosts = posts.filter((p) => !seenUids.has(p.uid));

  if (newPosts.length === 0) {
    console.log(`  → 새 글 없음 (총 ${posts.length}건 확인)`);
  } else {
    console.log(`  → 새 글 ${newPosts.length}건 발견: ${newPosts.map((p) => p.title).join(', ')}`);
    try {
      await sendNewPostsAlert(board.name, board.url, newPosts);
    } catch (err) {
      console.error(`[warn] 메일 발송 실패:`, (err as Error).message);
    }
  }

  // 현재 페이지에 보이는 모든 글을 확인 완료로 표시
  markSeen(board.id, posts.map((p) => p.uid));
}

async function runAllBoards(): Promise<void> {
  for (const board of BOARDS) {
    try {
      await checkBoard(board);
    } catch (err) {
      console.error(`[error] ${board.name} 확인 실패:`, err);
    }
  }
}

// 시작 시 최초 1회 실행 — 현재 글을 baseline으로 기록 (알림 없이)
async function initBaseline(): Promise<void> {
  console.log('[init] 기준선 설정 중...');
  for (const board of BOARDS) {
    try {
      const posts = await scrapePosts(board.url);
      markSeen(board.id, posts.map((p) => p.uid));
      console.log(`  → ${board.name}: ${posts.length}건 기록`);
    } catch (err) {
      console.error(`[init] ${board.name} 실패:`, err);
    }
  }
  console.log('[init] 기준선 설정 완료. 이후 새 글부터 알림 발송.');
}

async function main(): Promise<void> {
  // 환경변수 체크
  const required = ['NAVER_EMAIL', 'NAVER_PASSWORD', 'NOTIFY_EMAIL'];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length > 0) {
    console.error('[error] 필수 환경변수 누락:', missing.join(', '));
    process.exit(1);
  }

  await initBaseline();
  try {
    await sendStartupAlert();
  } catch (err) {
    // 시작 알림 실패 시 크래시 방지 — 모니터링 자체는 계속 실행
    console.error('[warn] 시작 알림 메일 발송 실패 (SMTP 설정 확인 필요):', (err as Error).message);
  }

  // 1분마다 확인
  const CRON_EXPR = process.env.CRON_EXPR ?? '* * * * *';
  console.log(`[cron] 스케줄 시작 — "${CRON_EXPR}"`);

  cron.schedule(CRON_EXPR, runAllBoards, { timezone: 'Asia/Seoul' });
}

main().catch((err) => {
  console.error('[fatal]', err);
  process.exit(1);
});
