"""Exploratory only (Phase 0): test hypotheses for Simsaw's sawdust volume against the Test1 run."""
import json, math, re, sys
import numpy as np
F="tests/fixtures/ngomi_1/"
def L(n): return json.load(open(F+n+".json"))
rl={r['log_uid']:r for r in L("run_logs")}; rr=L("run_log_results"); rb=L("run_board_results")
T={r['thickness_uid']:r for r in L("run_thicknesses")}; W={r['width_uid']:r for r in L("run_widths")}
wetT={r['dry_thickness']:r['wet_thickness'] for r in T.values()}; wetW={r['dry_width']:r['wet_width'] for r in W.values()}
pats={r['saw_pattern_uid']:r for r in L("run_saw_patterns")}
K=3.0
def expand(s):
    out=[]
    for tok in s.split():
        m=re.fullmatch(r"(\d+)\*(\d+)",tok)
        out += [float(m.group(2))]*int(m.group(1)) if m else [float(tok)]
    return out
def layout(p):
    left,cant,right=p['primary'].split('/')
    cw=wetW[float(cant)]
    xk=[]  # primary kerf intervals (positive side), mirrored
    x=cw/2
    for t in expand(right):
        xk.append((x,x+K)); x+=K+wetT[t]
    xk_outer=(x,x+K)
    sec=[wetT[t] for t in expand(p['secondary'])]
    tot=sum(sec)+K*(len(sec)-1); y=-tot/2; yk=[]
    for i,t in enumerate(sec):
        y+=t
        if i<len(sec)-1: yk.append((y,y+K)); y+=K
    yk_outer=[(-tot/2-K,-tot/2),(tot/2,tot/2+K)]
    return cw,xk,xk_outer,yk,yk_outer
def slab_x(Rh,Rv,a,b,n=40):
    xs=np.linspace(a,b,n); h=np.where(np.abs(xs)<Rh,2*Rv*np.sqrt(np.clip(1-(xs/Rh)**2,0,None)),0)
    return np.trapezoid(h,xs)
def slab_y(Rh,Rv,c,a,b,half,n=40):
    ys=np.linspace(a,b,n); u=(ys-c)/Rv
    hc=np.where(np.abs(u)<1,Rh*np.sqrt(np.clip(1-u**2,0,None)),0)
    return np.trapezoid(2*np.minimum(hc,half),ys)
res=[]
for r in rr:
    l=rl[r['log_uid']]; p=pats[r['saw_pattern_uid']]
    cw,xk,xko,yk,yko=layout(p)
    Lm=l['length']; D0=l['diameter']*10; tp=l['taper']; ov=l['ovality']; s=l['sweep']
    zs=np.arange(0.025,Lm,0.05); dz=50.0
    v_pin=v_pout=v_sin=v_sout=0.0
    for z in zs:
        D=D0+tp*z; Rh=D/2/math.sqrt(ov); Rv=D/2*math.sqrt(ov); c=-s*(1-((z-Lm/2)/(Lm/2))**2)
        for a,b in xk: v_pin+=2*slab_x(Rh,Rv,a,b)*dz
        v_pout+=2*slab_x(Rh,Rv,*xko)*dz
        for a,b in yk: v_sin+=slab_y(Rh,Rv,c,a,b,cw/2)*dz
        for a,b in yko: v_sout+=slab_y(Rh,Rv,c,a,b,cw/2)*dz
    bs=[b for b in rb if b['saw_pattern_uid']==r['saw_pattern_uid'] and b['log_uid']==r['log_uid']]
    edg=0; rs=0
    for b in bs:
        full = (b['board_type']==2 and abs((b['board_right']-b['board_left'])-cw)<0.01)
        wt=T[b['thickness_uid']]['wet_thickness']; ww=W[b['width_uid']]['wet_width']
        if not full: edg+=2*5.0*wt*b['board_length']*1000
        if b['resawn']: rs+=5.0*ww*b['board_length']*1000
    res.append((r['sawdust_volume'],v_pin/1e9,v_pout/1e9,v_sin/1e9,v_sout/1e9,edg/1e9,rs/1e9,l['log_no'],r['saw_pattern_uid']))
A=np.array(res)
ref=A[:,0]
combos={"pin+sin":A[:,1]+A[:,3],"pin+pout+sin":A[:,1]+A[:,2]+A[:,3],"pin+pout+sin+sout":A[:,1:5].sum(1),
"all kerfs+edger":A[:,1:6].sum(1),"all kerfs+edger+resaw":A[:,1:7].sum(1),"pin+sin+edger":A[:,1]+A[:,3]+A[:,5],"pin+pout+sin+edger":A[:,1]+A[:,2]+A[:,3]+A[:,5]}
for k,v in combos.items():
    rat=v/ref
    print(f"{k:24s} ratio mean {rat.mean():.4f} sd {rat.std():.4f} min {rat.min():.3f} max {rat.max():.3f}")
print("first rows (ref, pin, pout, sin, sout, edger, resaw):")
for row in res[:6]: print(["%.5f"%x for x in row[:7]], row[7:])

print("\n--- least squares on components (pin,pout,sin,sout,edger,resaw)")
X=A[:,1:7]; coef,*_=np.linalg.lstsq(X,ref,rcond=None); print("coef",np.round(coef,3),"resid sd",np.std(X@coef-ref)/ref.mean())
# scale by nominal/actual volume
sc=[]
for r in rr:
    l=rl[r['log_uid']]; Lm=l['length']; D0=l['diameter']/100; tp=l['taper']/1000
    act=math.pi/4*Lm*((D0)**2+D0*tp*Lm+(tp*Lm)**2/3)
    sc.append(r['log_volume']/act)
sc=np.array(sc)
for k,v in combos.items():
    rat=v*sc/ref
    print(f"scaled {k:24s} ratio mean {rat.mean():.4f} sd {rat.std():.4f} min {rat.min():.3f} max {rat.max():.3f}")
coef,*_=np.linalg.lstsq(X*sc[:,None],ref,rcond=None); print("scaled coef",np.round(coef,3),"resid sd",np.std((X*sc[:,None])@coef-ref)/ref.mean())
