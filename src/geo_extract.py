"""Clip Natural Earth land/borders to Borneo and check which sites/airports are on land.

Run: python -I src/geo_extract.py <natural-earth-dir> data/<biomass>.csv data/airports.dat data/borneo_geo.json
"""
import csv, json, math, sys
ne_dir, bio_csv, ap_dat, out_json = sys.argv[1:5]
BBOX = (107.0, -6.0, 120.5, 8.0)  # lon0, lat0, lon1, lat1

def ring_bbox(r):
    xs=[p[0] for p in r]; ys=[p[1] for p in r]; return min(xs),min(ys),max(xs),max(ys)
def hits(b): return not (b[2]<BBOX[0] or b[0]>BBOX[2] or b[3]<BBOX[1] or b[1]>BBOX[3])

land=json.load(open(f"{ne_dir}/ne_10m_land.geojson"))
polys=[]
for f in land["features"]:
    g=f["geometry"]; ps=g["coordinates"] if g["type"]=="MultiPolygon" else [g["coordinates"]]
    for p in ps:
        if hits(ring_bbox(p[0])): polys.append(p)
print("land polygons in bbox:", len(polys), "points:", sum(len(r) for p in polys for r in p))

def inside(x,y,ring):
    c=False; n=len(ring)
    for i in range(n):
        x1,y1=ring[i]; x2,y2=ring[i-1]
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: c=not c
    return c
def on_land(x,y):
    for p in polys:
        b=ring_bbox(p[0])
        if b[0]<=x<=b[2] and b[1]<=y<=b[3] and inside(x,y,p[0]) and not any(inside(x,y,h) for h in p[1:]):
            return True
    return False
def coast_km(x,y):
    best=1e9; kx=111.32*math.cos(math.radians(y)); ky=110.57
    for p in polys:
        for r in p:
            for i in range(len(r)):
                ax,ay=(r[i-1][0]-x)*kx,(r[i-1][1]-y)*ky; bx,by=(r[i][0]-x)*kx,(r[i][1]-y)*ky
                dx,dy=bx-ax,by-ay; L=dx*dx+dy*dy
                t=0 if L==0 else max(0,min(1,-(ax*dx+ay*dy)/L))
                d=math.hypot(ax+t*dx,ay+t*dy); best=min(best,d)
    return best

bio=list(csv.DictReader(open(bio_csv)))
print("\nBiomass sites in the sea:")
sea=[]
for r in bio:
    x,y=float(r["longitude"]),float(r["latitude"])
    if not on_land(x,y):
        d=coast_km(x,y); sea.append((r["location_id"],r["district"],float(r["production_kilotons"]),y,x,round(d,1)))
for s in sea: print("  ",s)
print("count:",len(sea),"kt:",round(sum(s[2] for s in sea),1))
near=[(r["location_id"],round(coast_km(float(r["longitude"]),float(r["latitude"])),1)) for r in bio if on_land(float(r["longitude"]),float(r["latitude"]))]
print("on land but within 2 km of coast:",[n for n in near if n[1]<2])

aps={}
for line in csv.reader(open(ap_dat)):
    if line[4] in ("PNK","PKN","BPN","TRK"): aps[line[4]]=(float(line[7]),float(line[6]))
print("\nairports on land:",{k:on_land(*v) for k,v in aps.items()})
# Which land polygon is TRK on? Is it the Borneo polygon?
def poly_of(x,y):
    for i,p in enumerate(polys):
        b=ring_bbox(p[0])
        if b[0]<=x<=b[2] and b[1]<=y<=b[3] and inside(x,y,p[0]): return i,len(p[0]),ring_bbox(p[0])
print("TRK polygon:",poly_of(*aps["TRK"]),"BPN coast km:",round(coast_km(*aps["BPN"]),2))

# region weighted centroids
regions={"West":["Ketapang","Sanggau"],"Central":["Kotawaringin Barat","Kotawaringin Timur"],"East":["Kutai Kartanegara","Paser"]}
print("\nregion centroids:")
for k,ds in regions.items():
    rs=[r for r in bio if r["district"] in ds]; kt=sum(float(r["production_kilotons"]) for r in rs)
    y=sum(float(r["latitude"])*float(r["production_kilotons"]) for r in rs)/kt; x=sum(float(r["longitude"])*float(r["production_kilotons"]) for r in rs)/kt
    print(f"  {k}: ({y:.3f},{x:.3f}) on_land={on_land(x,y)}")

# simplified geometry for the page
def dp(pts,tol):
    if len(pts)<4: return pts
    keep=[False]*len(pts); keep[0]=keep[-1]=True; stack=[(0,len(pts)-1)]
    while stack:
        a,b=stack.pop(); ax,ay=pts[a]; bx,by=pts[b]; dx,dy=bx-ax,by-ay; L=math.hypot(dx,dy)
        imax,dmax=-1,0
        for i in range(a+1,b):
            d=abs(dy*(pts[i][0]-ax)-dx*(pts[i][1]-ay))/L if L>1e-9 else math.hypot(pts[i][0]-ax,pts[i][1]-ay)
            if d>dmax: imax,dmax=i,d
        if dmax>tol: keep[imax]=True; stack+= [(a,imax),(imax,b)]
    return [p for p,k in zip(pts,keep) if k]
TOL=0.008
out_land=[]
for p in polys:
    b=ring_bbox(p[0])
    if (b[2]-b[0])*(b[3]-b[1]) < 0.0004 and not (b[0]<=aps["TRK"][0]<=b[2] and b[1]<=aps["TRK"][1]<=b[3]): continue  # drop specks
    rings=[[ [round(x,3),round(y,3)] for x,y in dp(r,TOL)] for r in p]
    if len(rings[0])>=4: out_land.append(rings)
bl=json.load(open(f"{ne_dir}/ne_10m_admin_0_boundary_lines_land.geojson"))
out_b=[]
for f in bl["features"]:
    g=f["geometry"]; ls=g["coordinates"] if g["type"]=="MultiLineString" else [g["coordinates"]]
    for l in ls:
        if hits(ring_bbox(l)): out_b.append([[round(x,3),round(y,3)] for x,y in dp(l,TOL)])
checks={r["location_id"]:{"on_land":on_land(float(r["longitude"]),float(r["latitude"])),"coast_km":round(coast_km(float(r["longitude"]),float(r["latitude"])),1)} for r in bio}
ap_checks={k:{"on_land":on_land(*v),"coast_km":round(coast_km(*v),1),"small_island":poly_of(*v) is not None and (poly_of(*v)[2][2]-poly_of(*v)[2][0])*(poly_of(*v)[2][3]-poly_of(*v)[2][1])<1.0} for k,v in aps.items()}
json.dump({"source":"Natural Earth 1:10m land and admin-0 land boundaries (public domain), clipped to Borneo and simplified","land":out_land,"borders":out_b,"site_checks":checks,"airport_checks":ap_checks},open(out_json,"w"),separators=(",",":"))
import os; print("\nwrote",out_json,os.path.getsize(out_json),"bytes; land polys",len(out_land),"border lines",len(out_b))
