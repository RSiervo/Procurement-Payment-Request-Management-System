import { Settings } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { authApi } from '../../api/misc'
import { Badge, Button, ButtonLink, Card, Input } from '../../components/ui'
import { useAuth, useUser } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'

/** Who the person is in the organisation. Their own preferences live on the Settings page. */
export function ProfilePage() {
  const user = useUser()
  const { refresh } = useAuth()
  const toast = useToast()
  const [names, setNames] = useState({ first_name: user.first_name, last_name: user.last_name })
  const [busy, setBusy] = useState(false)

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await authApi.updateProfile(names)
      refresh()
      toast.success('Profile updated.')
    } catch (error) {
      toast.error(error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Profile</h1>
        <ButtonLink to="/settings" icon={<Settings size={16} />}>Settings</ButtonLink>
      </div>

      <Card title="Your details">
        <form className="stack" onSubmit={saveProfile}>
          <div className="form-grid">
            <Input label="First name" value={names.first_name} required
                   onChange={(e) => setNames({ ...names, first_name: e.target.value })} />
            <Input label="Last name" value={names.last_name} required
                   onChange={(e) => setNames({ ...names, last_name: e.target.value })} />
          </div>
          <dl className="dl">
            <div><dt>Email</dt><dd>{user.email}</dd></div>
            <div><dt>Department</dt><dd>{user.department_name || '—'}</dd></div>
            <div><dt>Position</dt><dd>{user.position || '—'}</dd></div>
            <div><dt>Employee ID</dt><dd>{user.employee_id || '—'}</dd></div>
            <div><dt>Approver level</dt><dd>{user.approver_level_name || '—'}</dd></div>
            <div>
              <dt>Roles</dt>
              <dd className="row-wrap">{user.roles.map((role) => <Badge key={role} plain>{role.replace(/_/g, ' ')}</Badge>)}</dd>
            </div>
          </dl>
          <p className="xs muted">Department, position and roles are managed by your administrator.</p>
          <div><Button type="submit" variant="primary" loading={busy}>Save changes</Button></div>
        </form>
      </Card>
    </div>
  )
}
