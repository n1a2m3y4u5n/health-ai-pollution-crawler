import nodemailer from 'nodemailer';
import { Post } from './scraper';

const transporter = nodemailer.createTransport({
  host: 'smtp.naver.com',
  port: 465,
  secure: true,
  auth: {
    user: process.env.NAVER_EMAIL!,
    pass: process.env.NAVER_PASSWORD!,
  },
});

export async function sendStartupAlert(): Promise<void> {
  await transporter.sendMail({
    from: `"e-ICON 모니터" <${process.env.NAVER_EMAIL}>`,
    to: process.env.NOTIFY_EMAIL!,
    subject: '[e-ICON] 모니터링 시작됨',
    html: `
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Apple SD Gothic Neo','맑은 고딕',sans-serif;">
  <div style="max-width:600px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#185FA5;padding:20px 24px;">
      <h1 style="margin:0;color:#fff;font-size:18px;">e-ICON 게시판 모니터링 시작</h1>
    </div>
    <div style="padding:20px 24px;color:#333;">
      <p>모니터링이 정상적으로 시작되었습니다.</p>
      <ul style="padding-left:20px;line-height:2;">
        <li>공지사항: <a href="https://e-icon.or.kr/ko/%EA%B3%B5%EC%A7%80%EC%82%AC%ED%95%AD/" style="color:#185FA5;">바로가기</a></li>
        <li>Q&amp;A: <a href="https://e-icon.or.kr/ko/qa/" style="color:#185FA5;">바로가기</a></li>
      </ul>
      <p style="color:#666;font-size:13px;">새 글이 등록되면 이 주소로 즉시 알림을 보냅니다. (1분 간격 스캔)</p>
    </div>
    <div style="padding:16px 24px;background:#f8f8f8;color:#999;font-size:12px;">시작 시각: ${new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</div>
  </div>
</body>
</html>`,
  });
  console.log('[mailer] 시작 알림 메일 발송 완료');
}

export async function sendNewPostsAlert(
  boardName: string,
  boardUrl: string,
  newPosts: Post[]
): Promise<void> {
  if (newPosts.length === 0) return;

  const subject =
    newPosts.length === 1
      ? `[e-ICON] ${boardName}에 새 글: ${newPosts[0].title}`
      : `[e-ICON] ${boardName}에 새 글 ${newPosts.length}건`;

  const postListHtml = newPosts
    .map(
      (p) => `
      <tr>
        <td style="padding:10px 16px; border-bottom:1px solid #eee;">
          <a href="${p.url}" style="color:#185FA5; font-weight:600; text-decoration:none;">${p.title}</a>
        </td>
        <td style="padding:10px 16px; border-bottom:1px solid #eee; color:#666; white-space:nowrap;">${p.author}</td>
        <td style="padding:10px 16px; border-bottom:1px solid #eee; color:#666; white-space:nowrap;">${p.date}</td>
      </tr>`
    )
    .join('');

  const html = `
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:0; background:#f5f5f5; font-family:'Apple SD Gothic Neo', '맑은 고딕', sans-serif;">
  <div style="max-width:600px; margin:32px auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#185FA5; padding:20px 24px;">
      <h1 style="margin:0; color:#fff; font-size:18px;">e-ICON 게시판 알림</h1>
    </div>
    <div style="padding:20px 24px;">
      <p style="margin:0 0 16px; color:#333;">
        <strong>${boardName}</strong>에 새 글이 ${newPosts.length}건 등록되었습니다.
      </p>
      <table style="width:100%; border-collapse:collapse; border:1px solid #eee; border-radius:4px; overflow:hidden;">
        <thead>
          <tr style="background:#f8f8f8;">
            <th style="padding:10px 16px; text-align:left; font-size:13px; color:#555;">제목</th>
            <th style="padding:10px 16px; text-align:left; font-size:13px; color:#555;">작성자</th>
            <th style="padding:10px 16px; text-align:left; font-size:13px; color:#555;">작성일</th>
          </tr>
        </thead>
        <tbody>${postListHtml}</tbody>
      </table>
      <p style="margin:20px 0 0;">
        <a href="${boardUrl}" style="display:inline-block; background:#185FA5; color:#fff; padding:10px 20px; border-radius:4px; text-decoration:none; font-size:14px;">게시판 바로가기</a>
      </p>
    </div>
    <div style="padding:16px 24px; background:#f8f8f8; color:#999; font-size:12px;">
      이 메일은 자동 발송됩니다. 발신 전용 주소입니다.
    </div>
  </div>
</body>
</html>`;

  await transporter.sendMail({
    from: `"e-ICON 모니터" <${process.env.NAVER_EMAIL}>`,
    to: process.env.NOTIFY_EMAIL!,
    subject,
    html,
  });

  console.log(`[mailer] 메일 발송 완료 — ${boardName} 새 글 ${newPosts.length}건`);
}
