from __future__ import annotations
import networkx as nx
from app.core.physics import LinkParams

def _link(u: str,v: str,length: float,aerial: float) -> LinkParams: return LinkParams(f"{min(u,v)}-{max(u,v)}",u,v,length,aerial)
def get_preset(name: str) -> tuple[list[str],list[LinkParams]]:
    if name=="metro":
        nodes=list("ABCDEF"); specs=[("A","B",18,0),("B","C",30,1),("C","D",22,.5),("D","E",15,0),("E","F",28,1),("A","F",35,.8),("B","E",25,.6),("C","F",40,1)]
    elif name=="tiny":
        nodes=list("ABC"); specs=[("A","B",20,0),("B","C",25,1),("A","C",40,1)]
    else: raise ValueError(f"unknown topology preset: {name}")
    links=[_link(*s) for s in specs]; validate_links(links); return nodes,links
def build_graph(links: list[LinkParams]) -> nx.Graph:
    g=nx.Graph()
    for l in links: g.add_edge(l.u,l.v,link_id=l.link_id,length_km=l.length_km)
    return g
def link_lookup(links: list[LinkParams]) -> dict[str,LinkParams]: return {l.link_id:l for l in links}
def candidate_paths(graph: nx.Graph,src: str,dst: str,k: int) -> list[list[str]]:
    if k<=0:return []
    try:return [list(p) for _,p in zip(range(k),nx.shortest_simple_paths(graph,src,dst,weight="length_km"))]
    except (nx.NetworkXNoPath,nx.NodeNotFound):return []
def validate_links(links: list[LinkParams]) -> None:
    ids=set()
    for l in links:
        if l.link_id in ids:raise ValueError("duplicate link id")
        ids.add(l.link_id)
        if l.length_km<=0 or not 0<=l.aerial_fraction<=1:raise ValueError("invalid link parameters")
        if l.link_id!=f"{min(l.u,l.v)}-{max(l.u,l.v)}":raise ValueError("invalid link id")
    if links and not nx.is_connected(build_graph(links)):raise ValueError("disconnected topology")
