import { ArrowDown } from 'lucide-react'
import { Fragment } from 'react'

interface FlowStep {
  name: string
  detail?: string
  /** Approves after OPS has processed the request. */
  afterOps?: boolean
}

/** Visual route: Requester → approvals → OPS processing → approvals that follow OPS → Completed. */
export function WorkflowFlow({ steps, ops, horizontal }: { steps: FlowStep[]; ops: boolean; horizontal?: boolean }) {
  const approval = (step: FlowStep) => ({ name: step.name, detail: step.detail, terminal: false })
  const nodes = [
    { name: 'Requester', detail: 'Submits the request', terminal: true },
    ...steps.filter((step) => !(ops && step.afterOps)).map(approval),
    ...(ops ? [{ name: 'OPS Processing', detail: 'Receives and processes', terminal: true }] : []),
    ...steps.filter((step) => ops && step.afterOps).map(approval),
    { name: 'Completed', detail: undefined, terminal: true },
  ]
  return (
    <div className={`flow ${horizontal ? 'flow-horizontal' : ''}`}>
      {nodes.map((node, index) => (
        <Fragment key={`${node.name}-${index}`}>
          {index > 0 && <span className="flow-arrow" aria-hidden><ArrowDown size={16} /></span>}
          <div className="flow-node" data-kind={node.terminal ? 'terminal' : 'step'}>
            <div className="strong">{node.name}</div>
            {node.detail && <div className="xs muted">{node.detail}</div>}
          </div>
        </Fragment>
      ))}
    </div>
  )
}