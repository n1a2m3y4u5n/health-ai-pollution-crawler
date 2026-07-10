import axios from 'axios';
import * as cheerio from 'cheerio';

export interface Post {
  uid: string;
  title: string;
  url: string;
  date: string;
  author: string;
}

const BASE_URL = 'https://e-icon.or.kr';

export async function scrapePosts(pageUrl: string): Promise<Post[]> {
  const response = await axios.get(pageUrl, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
      'Accept-Language': 'ko-KR,ko;q=0.9',
    },
    timeout: 20000,
  });

  const $ = cheerio.load(response.data);
  const posts: Post[] = [];

  $('table tbody tr').each((_, row) => {
    const $row = $(row);
    const link = $row.find('td a[href*="uid="]').first();
    const href = link.attr('href');

    if (!href) return;

    const uidMatch = href.match(/uid=(\d+)/);
    if (!uidMatch) return;

    const uid = uidMatch[1];
    const title = link.text().trim();
    if (!title) return;

    const tds = $row.find('td');
    // 컬럼 순서: 번호 | 제목 | 작성자 | 작성일 | 추천 | 조회
    // 작성자와 날짜 위치를 텍스트 패턴으로 찾음
    let date = '';
    let author = '';

    tds.each((i, td) => {
      const text = $(td).text().trim();
      if (/^\d{4}\.\d{2}\.\d{2}$/.test(text)) {
        date = text;
        // 날짜 바로 앞 td가 작성자
        if (i > 0) {
          author = $(tds.get(i - 1)).text().trim();
        }
      }
    });

    posts.push({
      uid,
      title,
      url: `${BASE_URL}${href}`,
      date,
      author,
    });
  });

  return posts;
}
