from __future__ import annotations
import networkx as nx
import pytest
from app.core.topology import candidate_paths,get_preset,build_graph,validate_links

def test_presets_and_paths():
    for preset in ("tiny","metro"):
        nodes,links=get_preset(preset);g=build_graph(links);assert nx.is_connected(g)
        paths=candidate_paths(g,nodes[0],nodes[-1],4);assert len(paths)<=4
        lengths=[sum(g[a][b]["length_km"] for a,b in zip(p,p[1:])) for p in paths];assert lengths==sorted(lengths)
    with pytest.raises(ValueError):validate_links([get_preset("tiny")[1][0],get_preset("tiny")[1][0]])
