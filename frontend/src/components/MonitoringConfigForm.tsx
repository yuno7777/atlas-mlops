import type { MonitoringConfig } from '../api/types'
import { Field, Input, Toggle } from './ui'

export function MonitoringConfigForm({
  value,
  onChange,
}: {
  value: MonitoringConfig
  onChange: (config: MonitoringConfig) => void
}) {
  const update = <K extends keyof MonitoringConfig>(key: K, next: MonitoringConfig[K]) =>
    onChange({ ...value, [key]: next })

  return (
    <div className="stack-gap-16">
      <div className="form-grid-2">
        <Field
          label="PSI threshold"
          htmlFor="config-psi"
          hint="A feature drifts when its population stability index exceeds this value."
        >
          <Input
            id="config-psi"
            type="number"
            min={0.01}
            max={5}
            step={0.05}
            value={value.psi_threshold}
            onChange={(event) => update('psi_threshold', Number(event.target.value))}
          />
        </Field>
        <Field
          label="Feature drift share"
          htmlFor="config-drift-share"
          hint="Share of features that must drift for the deployment to be flagged."
        >
          <div className="input-with-suffix">
            <Input
              id="config-drift-share"
              type="number"
              min={1}
              max={100}
              step={1}
              value={Math.round(value.drift_share_threshold * 100)}
              onChange={(event) =>
                update('drift_share_threshold', Number(event.target.value) / 100)
              }
            />
            <span>%</span>
          </div>
        </Field>
        <Field
          label="Performance degradation"
          htmlFor="config-performance"
          hint="Allowed drop from the registered baseline on labelled predictions."
        >
          <div className="input-with-suffix">
            <Input
              id="config-performance"
              type="number"
              min={1}
              max={100}
              step={1}
              value={Math.round(value.performance_degradation_threshold * 100)}
              onChange={(event) =>
                update('performance_degradation_threshold', Number(event.target.value) / 100)
              }
            />
            <span>%</span>
          </div>
        </Field>
        <Field
          label="Minimum samples"
          htmlFor="config-min-samples"
          hint="Below this count, monitoring reports insufficient data."
        >
          <Input
            id="config-min-samples"
            type="number"
            min={5}
            max={100000}
            step={1}
            value={value.min_samples}
            onChange={(event) => update('min_samples', Number(event.target.value))}
          />
        </Field>
        <Field
          label="Analysis window"
          htmlFor="config-window"
          hint="Predictions considered by each monitoring run."
        >
          <div className="input-with-suffix">
            <Input
              id="config-window"
              type="number"
              min={1}
              max={720}
              step={1}
              value={value.window_hours}
              onChange={(event) => update('window_hours', Number(event.target.value))}
            />
            <span>hours</span>
          </div>
        </Field>
        <Field
          label="Retrain cooldown"
          htmlFor="config-cooldown"
          hint="Minimum gap between automatic retraining jobs."
        >
          <div className="input-with-suffix">
            <Input
              id="config-cooldown"
              type="number"
              min={1}
              max={720}
              step={1}
              value={value.auto_retrain_cooldown_hours}
              onChange={(event) =>
                update('auto_retrain_cooldown_hours', Number(event.target.value))
              }
            />
            <span>hours</span>
          </div>
        </Field>
      </div>
      <div className="config-toggle-row">
        <Toggle
          checked={value.auto_retrain_on_drift}
          onChange={(checked) => update('auto_retrain_on_drift', checked)}
          label="Automatically retrain when drift is detected"
        />
        <div>
          <strong>Retrain automatically on drift</strong>
          <p>
            Queues a training job with the incumbent algorithm and hyperparameters. Registration and
            promotion stay manual.
          </p>
        </div>
      </div>
    </div>
  )
}
