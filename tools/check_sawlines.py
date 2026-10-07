"""Phase 0 check: do saw-line positions derived from the pattern text reproduce every stored board position?"""
import json, re, collections
F="tests/fixtures/ngomi_1/"
def L(n): return json.load(open(F+n+".json"))
rb=L("run_board_results")
T={r['thickness_uid']:r for r in L("run_thicknesses")}; W={r['width_uid']:r for r in L("run_widths")}
wetT={r['dry_thickness']:r['wet_thickness'] for r in T.values()}; wetW={r['dry_width']:r['wet_width'] for r in W.values()}
pats={r['saw_pattern_uid']:r for r in L("run_saw_patterns")}; K=3.0
def expand(s):
    out=[]
    for tok in s.split():
        m=re.fullmatch(r"(\d+)\*(\d+)",tok)
        out += [float(m.group(2))]*int(m.group(1)) if m else [float(tok)]
    return out
def serialise(ts):
    out=[]; i=0
    while i<len(ts):
        j=i
        while j<len(ts) and ts[j]==ts[i]: j+=1
        out.append(f"{j-i}*{ts[i]:g}" if j-i>1 else f"{ts[i]:g}"); i=j
    return " ".join(out)
worst=0; n=0; stats=collections.Counter()
for uid,p in pats.items():
    left,cant,right=p['primary'].split('/')
    assert serialise(expand(p['secondary']))==p['secondary'] and serialise(expand(left))==left
    cw=wetW[float(cant)]
    sec=[wetT[t] for t in expand(p['secondary'])]; tot=sum(sec)+K*(len(sec)-1)
    ys=[]; y=-tot/2
    for t in sec: ys.append((y,y+t)); y+=t+K
    xs=[]; x=cw/2
    for t in expand(right): xs.append((x+K,x+K+wetT[t])); x+=K+wetT[t]
    for b in rb:
        if b['saw_pattern_uid']!=uid: continue
        n+=1
        if b['board_type']==2:
            lo,hi=ys[b['board_no']]
            e=max(abs(b['board_bottom']-lo),abs(b['board_top']-hi)); worst=max(worst,e)
            fw=abs((b['board_right']-b['board_left'])-cw)<0.05
            stats['cant full width' if fw else 'cant edged']+=1
            if fw: worst=max(worst,abs(b['board_left']+cw/2),abs(b['board_right']-cw/2))
        else:
            lo,hi=xs[b['board_no']]
            if b['board_type']==0: e=max(abs(b['board_right']+lo),abs(b['board_left']+hi))
            else: e=max(abs(b['board_left']-lo),abs(b['board_right']-hi))
            worst=max(worst,e); stats['sideboard']+=1
print("boards checked",n,"worst saw-line error (mm)",round(worst,4),dict(stats))
# widths of stored box vs product wet size
bad=0
for b in rb:
    t=T[b['thickness_uid']]['wet_thickness']; w=W[b['width_uid']]['wet_width']
    if b['board_type']==2: th=b['board_top']-b['board_bottom']; wd=b['board_right']-b['board_left']
    else: th=b['board_right']-b['board_left']; wd=b['board_top']-b['board_bottom']
    if abs(wd-w)>0.05: bad+=1
    if not b['resawn'] and abs(th-t)>0.05: bad+=1
print("boards whose stored box != wet product size:",bad)
