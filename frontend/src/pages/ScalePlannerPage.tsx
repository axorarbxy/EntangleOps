import { useMemo, useState } from 'react';
import { ArrowRight, Boxes, Cpu, Network, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

type Workload = 'shor' | 'grover' | 'simulation';
const whole = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

export function ScalePlannerPage() {
  const [workload, setWorkload] = useState<Workload>('shor');
  const [shorLogical, setShorLogical] = useState(1000);
  const [searchBits, setSearchBits] = useState(32);
  const [groverAncilla, setGroverAncilla] = useState(16);
  const [simulationSites, setSimulationSites] = useState(100);
  const [qubitsPerSite, setQubitsPerSite] = useState(2);
  const [simulationAncilla, setSimulationAncilla] = useState(20);
  const [encodingFactor, setEncodingFactor] = useState(100);
  const [reservePct, setReservePct] = useState(15);
  const [qubitsPerNode, setQubitsPerNode] = useState(1000);

  const logicalQubits = useMemo(() => {
    if (workload === 'shor') return shorLogical;
    if (workload === 'grover') return searchBits + groverAncilla;
    return simulationSites * qubitsPerSite + simulationAncilla;
  }, [workload, shorLogical, searchBits, groverAncilla, simulationSites, qubitsPerSite, simulationAncilla]);
  const footprint = useMemo(() => {
    const encoded = Math.ceil(logicalQubits * encodingFactor);
    const withReserve = Math.ceil(encoded * (1 + reservePct / 100));
    const nodes = Math.ceil(withReserve / qubitsPerNode);
    return { encoded, withReserve, nodes, links: Math.max(0, nodes - 1) };
  }, [logicalQubits, encodingFactor, reservePct, qubitsPerNode]);

  const numberInput = (label: string, value: number, change: (value: number) => void, min = 1, max = 1_000_000) => (
    <label className="form-field scale-input">
      {label}
      <input type="number" min={min} max={max} step="1" value={value} onChange={(event) => change(Math.max(min, Math.min(max, Number(event.target.value) || min)))} />
    </label>
  );

  return <>
    <div className="page-heading">
      <div><div className="eyebrow">ALGORITHM SCALE · CAPACITY PLANNING</div><h1>Qubit scale planner</h1><p>Translate a workload’s logical-qubit estimate into an illustrative physical-qubit and network-module footprint.</p></div>
    </div>

    <section className="scale-hero panel">
      <div className="scale-hero-icon"><Boxes size={23} /></div>
      <div><span className="scale-eyebrow">FROM ALGORITHM TO ARCHITECTURE</span><h2>What could scaling out require?</h2><p>Shor factoring, Grover search, and quantum simulation can demand far more qubits than a single device may provide. Set workload and hardware assumptions to explore the scale-up path.</p></div>
      <div className="scale-hero-badge"><Network size={15} /><span>Network-aware<br/>capacity sketch</span></div>
    </section>

    <div className="scale-layout">
      <section className="panel scale-config">
        <div className="panel-heading"><div><h2>1 · Describe the workload</h2><p>Pick an algorithm family and provide a logical-qubit estimate.</p></div></div>
        <div className="scale-workload-tabs" role="tablist" aria-label="Workload family">
          {([['shor', 'Shor factoring'], ['grover', 'Grover search'], ['simulation', 'Quantum simulation']] as const).map(([id, name]) => <button key={id} type="button" role="tab" aria-selected={workload === id} className={workload === id ? 'selected' : ''} onClick={() => setWorkload(id)}>{name}</button>)}
        </div>
        <div className="scale-fields">
          {workload === 'shor' ? <>
            {numberInput('Logical qubits from a Shor circuit estimate', shorLogical, setShorLogical, 1, 1_000_000)}
            <p className="scale-field-note">Enter a resource estimate for your target number and circuit design. Shor’s required width depends on the implementation and error-correction assumptions.</p>
          </> : workload === 'grover' ? <>
            {numberInput('Search-space width (input qubits)', searchBits, setSearchBits, 1, 1_000_000)}
            {numberInput('Oracle / work ancillas', groverAncilla, setGroverAncilla, 0, 1_000_000)}
            <p className="scale-field-note">For an address register of n bits, Grover represents 2ⁿ possible entries. Oracle work qubits vary with the predicate circuit.</p>
          </> : <>
            {numberInput('Modelled sites / orbitals', simulationSites, setSimulationSites, 1, 1_000_000)}
            {numberInput('Logical qubits per site', qubitsPerSite, setQubitsPerSite, 1, 1000)}
            {numberInput('Algorithm work ancillas', simulationAncilla, setSimulationAncilla, 0, 1_000_000)}
            <p className="scale-field-note">This simple mapping assumes a fixed qubit count per site; the encoding and simulation algorithm can change the actual circuit width.</p>
          </>}
          <div className="scale-logical-total"><div><small>WORKLOAD WIDTH</small><b>{whole.format(logicalQubits)} <span>logical qubits</span></b></div><Cpu size={22}/></div>
        </div>

        <div className="scale-divider" />
        <div className="panel-heading"><div><h2>2 · Set architecture assumptions</h2><p>These are editable planning inputs, not fixed model constants.</p></div></div>
        <div className="scale-fields">
          {numberInput('Physical qubits per logical qubit', encodingFactor, setEncodingFactor, 1, 1_000_000)}
          {numberInput('Additional capacity reserve (%)', reservePct, setReservePct, 0, 100)}
          {numberInput('Physical qubits per network module', qubitsPerNode, setQubitsPerNode, 1, 1_000_000_000)}
        </div>
        <div className="scale-assumption-callout"><ShieldCheck size={16}/><p>The physical-to-logical ratio depends on physical error rates, code family, target reliability, and layout. Choose a value from your own resource estimate; this planner does not prescribe an error-correction code.</p></div>
      </section>

      <aside className="scale-results">
        <section className="panel scale-footprint">
          <div className="panel-heading"><div><h2>Estimated footprint</h2><p>For the workload and assumptions you entered.</p></div></div>
          <div className="scale-total"><small>PLANNED PHYSICAL QUBITS</small><b>{whole.format(footprint.withReserve)}</b><span>{whole.format(logicalQubits)} logical × {whole.format(encodingFactor)} physical/logical + {reservePct}% reserve</span></div>
          <div className="scale-bar" aria-label="Logical to physical qubit comparison"><i style={{ width: `${Math.max(2, Math.min(100, (logicalQubits / footprint.withReserve) * 100))}%` }}/></div>
          <div className="scale-bar-legend"><span>Logical workload</span><b>{whole.format(logicalQubits)}</b></div>
          <div className="scale-bar-legend"><span>Encoded + reserve</span><b>{whole.format(footprint.withReserve)}</b></div>
          <div className="scale-metrics">
            <div><small>COMPUTE MODULES</small><b>{whole.format(footprint.nodes)}</b><span>at {whole.format(qubitsPerNode)} qubits each</span></div>
            <div><small>MINIMUM LINKS</small><b>{whole.format(footprint.links)}</b><span>to connect modules as a tree</span></div>
          </div>
          <p className="scale-link-note">The link count is a graph-theoretic minimum for connectivity; it does not estimate entanglement generation, swap success, routing, or throughput.</p>
        </section>
        <section className="panel scale-next-step"><div className="scale-next-icon"><Network size={18}/></div><div><h2>Next: explore the network layer</h2><p>Use EntangleOps’ simulator to compare routing policies and link fidelity under shared classical traffic.</p><Link to="/simulate" className="text-link">Open network simulation <ArrowRight size={14}/></Link></div></section>
      </aside>
    </div>

    <p className="scale-disclaimer">Planning sketch only. It converts your supplied logical width and architecture ratios into a rough capacity count. It does not compile circuits, select an error-correcting code, account for magic-state factories or connectivity overhead, or claim that a circuit can be partitioned across modules. <a href="https://www.nature.com/articles/s41586-024-08449-y" target="_blank" rel="noreferrer">Surface-code experiments illustrate why physical-to-logical overhead depends on code distance and measured error rates.</a></p>
  </>;
}
