from collections import deque
import sys

def solve():
    data = sys.stdin.buffer.read().split()
    idx = 0
    
    N, M, C = int(data[idx]), int(data[idx+1]), int(data[idx+2])
    idx += 3
    
    Ks = []
    for _ in range(C):
        Ks.append(int(data[idx])); idx += 1
    
    grid = []
    positions = [None, None]
    
    for i in range(N):
        row = list(data[idx].decode()); idx += 1
        for j, ch in enumerate(row):
            if ch == 'B':
                positions[0] = (i, j)
                row[j] = '.'
            elif ch == 'D':
                positions[1] = (i, j)
                row[j] = '.'
        grid.append(row)
    
    remaining = set()
    for i in range(N):
        for j in range(M):
            if grid[i][j] == '@':
                remaining.add((i, j))
    
    DMAP = {'U':(-1,0), 'D':(1,0), 'L':(0,-1), 'R':(0,1)}
    DIRS = [(-1,0,'U'),(1,0,'D'),(0,-1,'L'),(0,1,'R')]
    
    def bfs(start):
        dist = {start: 0}
        parent = {start: None}
        q = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc, _ in DIRS:
                nr, nc = r+dr, c+dc
                if 0<=nr<N and 0<=nc<M and (nr,nc) not in dist and grid[nr][nc] not in ('#','@'):
                    dist[(nr,nc)] = dist[(r,c)] + 1
                    parent[(nr,nc)] = (r,c)
                    q.append((nr,nc))
        return dist, parent
    
    def reconstruct(start, end, parent):
        if start == end:
            return []
        path = []
        cur = end
        while cur != start:
            prev = parent[cur]
            dr, dc = cur[0]-prev[0], cur[1]-prev[1]
            for d,dd,n in DIRS:
                if d==dr and dd==dc:
                    path.append(n); break
            cur = prev
        return list(reversed(path))
    
    def bomb_set(r, c, K):
        res = set()
        for dr, dc, _ in DIRS:
            for s in range(1, K+1):
                nr, nc = r+dr*s, c+dc*s
                if not (0<=nr<N and 0<=nc<M) or grid[nr][nc]=='#':
                    break
                if (nr,nc) in remaining:
                    res.add((nr,nc)); break
        return res
    
    def make_plan(pi):
        pos = positions[pi]
        K = Ks[pi]
        dist, parent = bfs(pos)
        
        best_score, best_target = -1, None
        for r in range(N):
            for c in range(M):
                p = (r,c)
                if p not in dist:
                    continue
                d = dist[p]
                bs = bomb_set(r,c,K)
                if not bs:
                    continue
                score = len(bs)*10000 - d
                if score > best_score:
                    best_score, best_target = score, p
        
        if best_target is None:
            return ['B']
        
        path = reconstruct(pos, best_target, parent)
        return path + ['B']
    
    queues = [[], []]
    out = []
    step = 0
    
    while remaining and step < 99999:
        pi = step % C
        
        if not queues[pi]:
            queues[pi] = make_plan(pi)
        
        act = queues[pi].pop(0)
        out.append(act)
        
        if act == 'B':
            r, c = positions[pi]
            destroyed = bomb_set(r, c, Ks[pi])
            for br, bc in destroyed:
                remaining.discard((br,bc))
                grid[br][bc] = '.'
            # 폭탄 이후 모든 플레이어 재계획
            queues[0].clear()
            queues[1].clear()
        else:
            dr, dc = DMAP[act]
            positions[pi] = (positions[pi][0]+dr, positions[pi][1]+dc)
        
        step += 1
    
    print(''.join(out))

solve()
