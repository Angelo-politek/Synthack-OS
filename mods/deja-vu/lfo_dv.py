"""Déjà Vu LFO patch logic, faithfully ported from Bezronczek's MIT Workbench source.
Copyright (c) 2026 Bezronczek. See THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations
from typing import Iterable

SECTION=3; BASE=0x40000400; DVF=7; DVT=8; N=9; LAST=8
CAVE=0x402ba000; CAVE_LEN=0x1780; CAVE2=0x402b9b00; CAVE2_LEN=0x500
L=dict(GEN=0,NAMES=0x40,STRINGS=0x80,MARK=0xa0,START0=0xc0,START1=0x100,START2=0x140,FLAGS=0x180,SHEET_VEC=0x1a0,SHEET_OBJS=0x1b0,GLYPH_DV=0x300,SET_ARR=0x3a0,SET_OBJS_DVF=0x440,SET_OBJS_DVT=0x4b0,MASTER_DVF=0x520,MASTER_DVT=0x590,LIVE_DVF=0x600,LIVE_DVT=0x670,PROB=0x6e0,SLIDE2=0x700,MODEHELP=0x740,LASTWAVE=0x760,LENSTR=0x770,LENTAB=0x780,HOOK1=0x7a0,HOOK2=0x7c0,CODE_DVF=0x920,CODE_DVT=0xb40,SLOTS=0xd80)
L2=dict(ICONVEC=0,ICONHELP=0x10,ICONOBJS=0x30,ICONDATA=0xc0)
GEN_TABLE=0x40245838; NAME_TABLE=0x401d44c4; FLAG_TABLE=0x4023ff00
START_TABLES=(0x402457e4,0x40245800,0x4024581c); BITMAP_VPTR=0x40240c3c; GLYPH_BLOCKS=0x4031b858; GLYPH_MASK=0x4031b80c; GLYPH_STRIDE=0x4c
TILE_MASK=0x402d7e1c; TILE_EXTRA=0x00ffffff; MODE_ICON_MASK=0x40304cec; MODE_NAMES=0x401d44e0; SHEET_GET=0x400f9258; NO_SLIDE_RETURN=0x400f32ec
OPERAND_SITES=((0x40119154,CAVE+L['GEN']),(0x40119460,CAVE+L['GEN']),(0x400702e4,CAVE+L['SHEET_VEC']),(0x4014f82c,CAVE+L['SHEET_VEC']),(0x400f32f2,CAVE+L['FLAGS']),*[ (a,CAVE+L['SET_ARR']+12*k) for k,a in enumerate((0x400f339c,0x400f33b0,0x400f33be,0x400f33cc,0x400f33de,0x400f33ec,0x400f33fa))],(0x400f3420,CAVE+L['SET_ARR']),(0x400f347c,CAVE+L['SET_ARR']),(0x40070338,CAVE2+L2['ICONHELP']),(0x40119032,CAVE+L['START0']),(0x4011934e,CAVE+L['START0']),(0x40119068,CAVE+L['START1']),(0x4011937e,CAVE+L['START1']),(0x4011905c,CAVE+L['START2']),(0x40119374,CAVE+L['START2']))
COUNT_BYTES=((0x400f323b,LAST),(0x400f325d,LAST),(0x400f32f1,N),(0x400f32fb,256-N),(0x400f3307,256-N),(0x40118ffd,LAST),(0x40119003,LAST),(0x401192eb,LAST),(0x401192f1,LAST),(0x4006fa9f,LAST))
WAVE_MAX=(0x4022e7f0,0x4022e9f8); WIDGET=0x400f32c0; NAME_FORMATTERS=((0x4006fab2,CAVE+L['NAMES'],'lea'),(0x4006fb26,CAVE+L['MODEHELP'],'jsr')); EVAL_HOOKS=((0x40118fe2,8,CAVE+L['HOOK1'],7),(0x40119312,6,CAVE+L['HOOK2'],1))
REGIONS=tuple(sorted(((CAVE2,CAVE2+CAVE2_LEN,'MODE cell pictures'),(CAVE,CAVE+CAVE_LEN,'DV code/names/pictures'),(0x4006fa9e,0x4006fb42,'names'),(0x400702e0,0x40070340,'pictures'),(0x400f3238,0x400f3482,'WAVE widget'),(0x4014f820,0x4014f840,'pictures'),(0x40118fe0,0x40119160,'LFO eval 1'),(0x401192e8,0x40119468,'LFO eval 2'),(0x4022e7e4,0x4022e818,'LFO1 range'),(0x4022e9ec,0x4022ea20,'LFO2 range')),key=lambda x:x[0]))

def off(a:int)->int:return a-BASE
def b32(v:int)->bytes:return (v&0xffffffff).to_bytes(4,'big')
def label(s): return ('label',s)
def branch(op,s): return ('branch',op,s)
def asm(items):
 out=bytearray(); labels={}; fix=[]
 for item in items:
  if isinstance(item,tuple) and item[0]=='label': labels[item[1]]=len(out)
  elif isinstance(item,tuple) and item[0]=='branch': fix.append((len(out),item[1],item[2])); out.extend(item[1].to_bytes(2,'big')+b'\0\0')
  else: out.extend(item)
 for at,op,to in fix:
  d=labels[to]-(at+2)
  if not -32768<=d<=32767 or not d: raise ValueError('bad branch')
  out[at+2:at+4]=(d&0xffff).to_bytes(2,'big')
 return bytes(out)
def xorshift(seed): return bytes.fromhex('2039')+b32(seed)+bytes.fromhex('66000008203c2f6e2b1d2200e189eb89b3802200e089e089e289b3802200eb89b38023c0')+b32(seed)
def generator(slots,seed,trig):
 B=lambda o,s:branch(o,s); Q=lambda reg,v:bytes((0x70|(reg<<1),v))
 rnd=xorshift(seed); top=bytes.fromhex('2200e089e089e089')
 i=[bytes.fromhex('4feffff448d7001c202f0010721ce2a8220ae68902810000ffff243c0000cccd4c0210007412e4a902810000001f2401ed89e98ad28241f9')+b32(slots)+bytes.fromhex('d1c1220ab2a8000c'),B(0x6700,'owned'),bytes.fromhex('42902141000c'),label('owned'),bytes.fromhex('240052822610'),B(0x6700,'fresh')]
 if trig:i += [bytes.fromhex('4a2a0001'),B(0x6700,'notrig'),bytes.fromhex('42a800042082'),B(0x6000,'out'),label('notrig')]
 i += [bytes.fromhex('b483'),B(0x6700,'out'),bytes.fromhex('53832200928302810000000f0c810000000f'),B(0x6700,'out'),B(0x6000,'step'),label('fresh'),bytes.fromhex('43e800107620'),label('fill'),rnd,bytes.fromhex('12c05383'),B(0x6600,'fill'),bytes.fromhex('42a8000442a80030'),label('step'),bytes.fromhex('208224280004382b000402840000ffffe08c02840000007f7600162b00060c8300000004'),B(0x6300,'lenok'),bytes.fromhex('7604'),label('lenok'),bytes.fromhex('7202e7a926015282b483'),B(0x6500,'nowrap'),bytes.fromhex('4282'),label('nowrap'),bytes.fromhex('0c8400000040'),B(0x6500,'replace'),bytes.fromhex('048400000040e58c'),rnd,top,bytes.fromhex('b284'),B(0x6400,'store'),bytes.fromhex('e088e0880280000000ff4c030000e0882400'),B(0x6000,'store'),label('replace'),bytes.fromhex('723f9284e5892801'),rnd,top,bytes.fromhex('b284'),B(0x6400,'store'),bytes.fromhex('e088e08811802810'),label('store'),bytes.fromhex('21420004'),label('out'),bytes.fromhex('24280004103028100280000000ff0480000000807218e3a84cd7001c4fef000c4e75')]
 return asm(i)
def step_tile(levels,widths,wrap):
 edges=[0]
 for w in widths:edges.append(edges[-1]+w)
 out=[]
 for x in range(28):
  k=sum(e<=x for e in edges)-1; ys={levels[k]}
  def span(a,b):ys.update(range(min(a,b),max(a,b)+1))
  if x==0 and wrap is True:span(0,14)
  elif x==0 and wrap=='closed':span(levels[-1],levels[0])
  elif x>0 and x in edges:span(levels[k-1],levels[k])
  w=0
  for y in ys:w|=0x80000000>>(14-y)
  out.append(w)
 return out
DV_GLYPH=("..###############..",".#...............#.",".#...............#.",".#...............#.",".#...............#.",".#.....##........#.",".#.....##..##....#.",".#.##..##..##....#.",".#.##..##..##.##.#.",".#.##..##..##.##.#.",".#.##.###.###.##.#.",".#.#############.#.",".#...............#.",".#...............#.",".#...............#.",".#...............#.","..###############..")
DIGITS={
 '1':('..#..','.##..','..#..','..#..','..#..','..#..','.###.'),
 '2':('.###.','#...#','....#','...#.','..#..','.#...','#####'),
 '3':('####.','....#','....#','.###.','....#','....#','####.'),
 '4':('...#.','..##.','.#.#.','#..#.','#####','...#.','...#.'),
 '6':('.###.','#....','#....','####.','#...#','#...#','.###.'),
 '8':('.###.','#...#','#...#','.###.','#...#','#...#','.###.'),
}
LENGTHS=('2','4','8','16','32')
def build_section(raw:bytes)->bytes:
 out=bytearray(raw); cave=bytearray(CAVE_LEN); cave2=bytearray(CAVE2_LEN)
 def put(pos,data): cave[pos:pos+len(data)]=data
 def put2(pos,data): cave2[pos:pos+len(data)]=data
 def take(a,n): return raw[off(a):off(a)+n]
 code=(generator(CAVE+L['SLOTS'],CAVE+L['PROB']+4,False),generator(CAVE+L['SLOTS'],CAVE+L['PROB']+4,True))
 if L['CODE_DVF']+len(code[0])>L['CODE_DVT'] or L['CODE_DVT']+len(code[1])>L['SLOTS']: raise ValueError('layout')
 put(L['GEN'],take(GEN_TABLE,28)); put(L['GEN']+4*DVF,b32(CAVE+L['CODE_DVF'])); put(L['GEN']+4*DVT,b32(CAVE+L['CODE_DVT']))
 put(L['NAMES'],take(NAME_TABLE,28))
 for n,k in (('DV-F',0),('DV-T',1)):
  put(L['NAMES']+4*(7+k),b32(CAVE+L['STRINGS']+8*k)); put(L['STRINGS']+8*k,n.encode())
 put(L['MARK'],b'LFO9 DV-F/DV-T preview 2026-09-23'); put(L['CODE_DVF'],code[0]); put(L['CODE_DVT'],code[1])
 for a,n,h,reg in EVAL_HOOKS:
  head=take(a,n); body=head+bytes.fromhex('0c83')+b32(DVF)+bytes.fromhex('6604')+bytes((0x70|(reg<<1),0,0x4e,0x75))+bytes.fromhex('0c83')+b32(DVT)+bytes.fromhex('6602')+bytes((0x70|(reg<<1),1,0x4e,0x75)); put(h-CAVE,body)
 for t,p in zip(START_TABLES,(L['START0'],L['START1'],L['START2'])): put(p,take(t,28))
 put(L['FLAGS'],take(FLAG_TABLE,7)+bytes((1,1)))
 put(L['SHEET_VEC'],b32(CAVE+L['SHEET_OBJS'])+b32(CAVE+L['SHEET_OBJS']+N*0x1c)*2)
 for k in range(N):
  data=GLYPH_BLOCKS+k*GLYPH_STRIDE if k<7 else CAVE+L['GLYPH_DV']
  put(L['SHEET_OBJS']+k*0x1c,b32(BITMAP_VPTR)+b32(0x13)+b32(0x11)+b32(1)+b32(data)+b32(GLYPH_MASK)+b32(0))
 for x in range(19):
  w=0
  for y in range(17):
   if DV_GLYPH[y][x]=='#':w|=0x80000000>>y
  put(L['GLYPH_DV']+4*x,b32(w))
 levels=(3,11,6,13,1,9,4,12); widths=(4,3,4,3,4,3,4,3)
 for n,k,objs,live,master,wrap in (('DV-F',0,L['SET_OBJS_DVF'],L['LIVE_DVF'],L['MASTER_DVF'],'closed'),('DV-T',1,L['SET_OBJS_DVT'],L['LIVE_DVT'],L['MASTER_DVT'],True)):
  put(L['SET_ARR']+12*(7+k),b32(CAVE+objs)+b32(CAVE+objs+4*0x1c)*2)
  for v in range(4):put(objs+v*0x1c,b32(BITMAP_VPTR)+b32(28)+b32(15)+b32(1)+b32(CAVE+live)+b32(TILE_MASK)+b32(TILE_EXTRA))
  for c,w in enumerate(step_tile(levels,widths,wrap)):
   put(master+4*c,b32(w))
   put(live+4*c,b32(w))
 put(L['SLIDE2'],bytes.fromhex('23c5')+b32(CAVE+L['LASTWAVE'])+bytes.fromhex('4e714e714e710c85000000066d062ebc')+b32(NO_SLIDE_RETURN)+bytes.fromhex('4e75'))
 for k,t in enumerate(LENGTHS):put(L['LENSTR']+3*k,t.encode()) ; put(L['LENTAB']+4*k,b32(CAVE+L['LENSTR']+3*k))
 put(L['MODEHELP'],bytes.fromhex('41f9')+b32(MODE_NAMES)+bytes.fromhex('2039')+b32(CAVE+L['LASTWAVE'])+bytes.fromhex('5f800c8000000001620641f9')+b32(CAVE+L['LENTAB'])+bytes.fromhex('4e75'))
 for k,t in enumerate(LENGTHS):
  g=[['.']*19 for _ in range(17)]
  for x in range(2,17):g[0][x]=g[16][x]='#'
  for y in range(1,16):g[y][1]=g[y][17]='#'
  x0=7 if len(t)==1 else 4
  for j,ch in enumerate(t):
   for r,row in enumerate(DIGITS[ch]):
    for cx,c in enumerate(row):
     if c=='#':g[5+r][x0+6*j+cx]='#'
  for x in range(19):
   w=0
   for y in range(17):
    if g[y][x]=='#':w|=0x80000000>>(16-y)
   put2(L2['ICONDATA']+k*0x4c+4*x,b32(w))
  put2(L2['ICONOBJS']+k*0x1c,b32(BITMAP_VPTR)+b32(0x13)+b32(0x11)+b32(1)+b32(CAVE2+L2['ICONDATA']+k*0x4c)+b32(MODE_ICON_MASK)+b32(0))
 put2(L2['ICONVEC'],b32(CAVE2+L2['ICONOBJS'])+b32(CAVE2+L2['ICONOBJS']+5*0x1c)*2)
 put2(L2['ICONHELP'],bytes.fromhex('2239')+b32(CAVE+L['LASTWAVE'])+bytes.fromhex('5f810c8100000001620a223c')+b32(CAVE2+L2['ICONVEC'])+bytes.fromhex('2f4100044ef9')+b32(SHEET_GET))
 out[off(CAVE):off(CAVE)+CAVE_LEN]=cave;out[off(CAVE2):off(CAVE2)+CAVE2_LEN]=cave2
 for a,target in OPERAND_SITES:out[off(a)+2:off(a)+6]=b32(target)
 for a,v in COUNT_BYTES:out[off(a)]=v
 for a in WAVE_MAX:out[off(a):off(a)+4]=b32(LAST<<8)
 out[off(WIDGET):off(WIDGET)+16]=out[off(WIDGET)+2:off(WIDGET)+18];out[off(WIDGET)+16:off(WIDGET)+22]=bytes.fromhex('4eb9')+b32(CAVE+L['SLIDE2'])
 for a,target,kind in NAME_FORMATTERS:out[off(a):off(a)+28]=(bytes.fromhex('41f9') if kind=='lea' else bytes.fromhex('4eb9'))+b32(target)+bytes.fromhex('41f02c00')+bytes.fromhex('4e71')*9
 for a,n,target,_ in EVAL_HOOKS:out[off(a):off(a)+n]=bytes.fromhex('4eb9')+b32(target)+(bytes.fromhex('4e71') if n==8 else b'')
 return bytes(out)
def is_patched(raw:bytes)->bool:return raw[off(CAVE+L['STRINGS']):off(CAVE+L['STRINGS'])+4]==b'DV-F'
