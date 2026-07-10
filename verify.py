import sys

def verify(grid_input, actions):
    lines = grid_input.strip().split('\n')
    first = lines[0].split()
    N, M, C = int(first[0]), int(first[1]), int(first[2])
    
    Ks = list(map(int, lines[1].split()))
    
    grid = []
    positions = [None, None]
    
    for i in range(N):
        row = list(lines[2+i])
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
                remaining.add((i,j))
    
    DMAP = {'U':(-1,0), 'D':(1,0), 'L':(0,-1), 'R':(0,1)}
    DIRS = [(-1,0),(1,0),(0,-1),(0,1)]
    
    for step, act in enumerate(actions):
        pi = step % C
        pos = positions[pi]
        
        if act == 'B':
            r, c = pos
            for dr, dc in DIRS:
                for s in range(1, Ks[pi]+1):
                    nr, nc = r+dr*s, c+dc*s
                    if not (0<=nr<N and 0<=nc<M) or grid[nr][nc]=='#':
                        break
                    if (nr,nc) in remaining:
                        remaining.discard((nr,nc))
                        grid[nr][nc] = '.'
                        break
        elif act in DMAP:
            dr, dc = DMAP[act]
            nr, nc = pos[0]+dr, pos[1]+dc
            if not (0<=nr<N and 0<=nc<M):
                print(f"Step {step}: 범위 밖 이동 오류!")
                return False
            if grid[nr][nc] in ('#', '@'):
                print(f"Step {step}: 장애물/블럭으로 이동 오류! grid[{nr}][{nc}]={grid[nr][nc]}")
                return False
            positions[pi] = (nr, nc)
    
    if remaining:
        print(f"미파괴 블럭 {len(remaining)}개: {remaining}")
        return False
    
    print(f"성공! 총 행동수: {len(actions)}")
    return True

# 테스트 1
test1_input = """3 3 1
1
B..
.@.
..."""
output1 = "RB"
verify(test1_input, output1)

# 테스트 2
test2_input = """1 5 1
2
B...@"""
output2 = "RRB"
verify(test2_input, output2)

# 테스트 3
test3_input = """3 3 2
1 1
B.D
.@.
..."""
output3 = "RLB"
verify(test3_input, output3)

# 추가 테스트
test4_input = """5 5 2
2 1
B.#.D
..#..
@.#.@
..#..
..@.."""
output4 = "DDRBDDDDDDLLB"
print("테스트4:", end=" ")
verify(test4_input, output4)

test5_input = """5 7 1
3
B......
.......
...@...
.......
......@"""
output5 = "DDDDRRRB"
print("테스트5:", end=" ")
verify(test5_input, output5)
