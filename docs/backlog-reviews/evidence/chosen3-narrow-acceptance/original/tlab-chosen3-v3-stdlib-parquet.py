"""Small, bounded flat Parquet reader for forensic synthetic artifacts; stdlib only."""
import struct
from compression import zstd
class Compact:
 def __init__(self,raw):self.raw=raw;self.i=0
 def take(self,n):
  assert n>=0 and self.i+n<=len(self.raw);v=self.raw[self.i:self.i+n];self.i+=n;return v
 def u(self):
  n=0;s=0
  for _ in range(10):
   b=self.take(1)[0];n|=(b&127)<<s
   if b<128:return n
   s+=7
  raise AssertionError('unbounded thrift integer')
 def val(self,t):
  if t==1:return True
  if t==2:return False
  if t==3:return int.from_bytes(self.take(1),'little',signed=True)
  if t in [4,5,6]:u=self.u();return (u>>1)^-(u&1)
  if t==7:return struct.unpack('<d',self.take(8))[0]
  if t==8:return self.take(self.u())
  if t in [9,10]:
   h=self.take(1)[0];size=h>>4
   if size==15:size=self.u()
   assert size<=100000
   return [self.val(h&15) for _ in range(size)]
  if t==11:
   size=self.u();assert size<=100000
   if not size:return {}
   h=self.take(1)[0];return {self.val(h>>4):self.val(h&15) for _ in range(size)}
  if t==12:return self.obj()
  raise AssertionError(('unsupported thrift type',t))
 def obj(self):
  d={};last=0
  for _ in range(10000):
   h=self.take(1)[0]
   if h==0:return d
   last=last+(h>>4) if h>>4 else self.val(4);assert last not in d
   d[last]=self.val(h&15)
  raise AssertionError('unbounded thrift fields')
def footer(raw):
 assert len(raw)<8*1024*1024 and raw[:4]==raw[-4:]==b'PAR1'
 length=int.from_bytes(raw[-8:-4],'little');assert length<=len(raw)-12
 p=Compact(raw[-8-length:-8]);f=p.obj();assert p.i==length;return f
def hybrid(raw,width,count):
 assert 0<=width<=64 and count<=100000;p=Compact(raw);out=[]
 while len(out)<count:
  h=p.u()
  if h&1:
   n=(h>>1)*8;assert n>0 and n<=100008;packed=int.from_bytes(p.take((n*width+7)//8),'little');mask=(1<<width)-1
   out.extend((packed>>(i*width))&mask for i in range(n))
  else:
   n=h>>1;assert n>0 and n<=100000;v=int.from_bytes(p.take((width+7)//8),'little');out.extend([v]*n)
 return out[:count]
def plain(raw,physical,count):
 if physical in [1,2,4,5]:
  code={1:'i',2:'q',4:'f',5:'d'}[physical];size=struct.calcsize(code);assert len(raw)>=count*size;return list(struct.unpack('<'+str(count)+code,raw[:count*size]))
 if physical==0:return [bool((raw[i//8]>>(i%8))&1) for i in range(count)]
 if physical==6:
  p=Compact(raw);out=[]
  for _ in range(count):n=int.from_bytes(p.take(4),'little');out.append(p.take(n).decode('utf8'))
  assert p.i==len(raw);return out
 raise AssertionError(('unsupported physical type',physical))
def table(raw,selected=None):
 f=footer(raw);schema=f[2];assert schema[0][5]==len(schema)-1
 leaves={e[4].decode():e for e in schema[1:]};assert all(e.get(5,0)==0 for e in schema[1:]);cols={name:[] for name in leaves if selected is None or name in selected};total=0;codecs=set();encodings=set()
 for rg in f.get(4,[]):
  nrows=rg[3];total+=nrows
  for cc in rg[1]:
   md=cc[3];path=md[3];assert len(path)==1;name=path[0].decode();codecs.add(md[4]);encodings.update(md[2])
   if name not in cols:continue
   assert md[5]==nrows and md[4] in [0,6]
   start=min(md[9],md.get(11,md[9]));end=start+md[7];pos=start;values=[];dictionary=None;definition=leaves[name].get(3,0)
   assert definition in [0,1]
   while pos<end and len(values)<nrows:
    p=Compact(raw[pos:end]);h=p.obj();pos+=p.i;body=raw[pos:pos+h[3]];pos+=h[3]
    if md[4]==6:
     assert 0<=h[2]<=1024*1024;dec=zstd.ZstdDecompressor();body=dec.decompress(body,max_length=h[2]+1);assert dec.eof and not dec.unused_data
    assert len(body)==h[2]
    if h[1]==2:
     dh=h[7];assert dh[2]==0;dictionary=plain(body,md[1],dh[1]);continue
    assert h[1]==0,('unsupported page type',h[1]);dh=h[5];count=dh[1];assert count<=100000
    if definition:
     size=int.from_bytes(body[:4],'little');defs=hybrid(body[4:4+size],1,count);body=body[4+size:]
    else:defs=[1]*count
    present=sum(defs)
    if dh[2]==0:items=plain(body,md[1],present)
    else:
     assert dh[2] in [2,8] and dictionary is not None,('unsupported encoding',dh[2]);indices=hybrid(body[1:],body[0],present);items=[dictionary[j] for j in indices]
    it=iter(items);values.extend(next(it) if d else None for d in defs)
   assert len(values)==nrows,(name,len(values),nrows);cols[name].extend(values)
 assert total==f[3] and all(len(v)==total for v in cols.values())
 return {'schema':{n:(e.get(1),e.get(3)) for n,e in leaves.items()},'columns':cols,'row_count':total,'codecs':sorted(codecs),'encodings':sorted(encodings)}
