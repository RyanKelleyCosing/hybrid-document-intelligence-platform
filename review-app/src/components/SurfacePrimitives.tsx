import {
  useId,
  type ElementType,
  type HTMLAttributes,
  type ReactNode,
  type TableHTMLAttributes,
} from "react";

export type StatusBadgeTone =
  | "accent"
  | "danger"
  | "neutral"
  | "success"
  | "warning";

type SurfaceElement = "article" | "aside" | "div" | "section";

type SurfaceContainerProps = HTMLAttributes<HTMLElement> & {
  as?: SurfaceElement;
  children: ReactNode;
};

type SectionHeadingProps = {
  actions?: ReactNode;
  className?: string;
  description?: ReactNode;
  title: ReactNode;
};

type SurfaceDialogProps = HTMLAttributes<HTMLElement> & {
  actions?: ReactNode;
  as?: SurfaceElement;
  badge?: ReactNode;
  children?: ReactNode;
  description?: ReactNode;
  title: ReactNode;
};

type SurfaceMetricCardProps = HTMLAttributes<HTMLElement> & {
  as?: SurfaceElement;
  badge?: ReactNode;
  detail?: ReactNode;
  eyebrow?: ReactNode;
  title?: ReactNode;
  value: ReactNode;
};

type SurfaceBarRowProps = HTMLAttributes<HTMLDivElement> & {
  detail?: ReactNode;
  label: ReactNode;
  progress: number;
  value: ReactNode;
};

type SurfaceColumnChartItem = {
  detail?: ReactNode;
  height: number;
  id?: string;
  label: ReactNode;
  tone?: StatusBadgeTone;
  value: ReactNode;
};

type SurfaceColumnChartProps = HTMLAttributes<HTMLDivElement> & {
  items: readonly SurfaceColumnChartItem[];
};

type SurfaceTimelineItemProps = HTMLAttributes<HTMLElement> & {
  as?: SurfaceElement;
  badge?: ReactNode;
  children?: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  markerState?: string;
  title: ReactNode;
};

type SurfaceTableFrameProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
};

type SurfaceTableProps = TableHTMLAttributes<HTMLTableElement> & {
  children: ReactNode;
};

type StatusBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode;
  tone?: StatusBadgeTone;
};

function joinClassNames(
  ...classNames: Array<string | false | null | undefined>
): string {
  return classNames.filter(Boolean).join(" ");
}

export function SurfacePanel({
  as = "section",
  children,
  className,
  ...rest
}: SurfaceContainerProps) {
  const Component = as as ElementType;

  return (
    <Component
      className={joinClassNames("surface-panel", "surface-card", "section-stack", className)}
      {...rest}
    >
      {children}
    </Component>
  );
}

export function SurfaceCard({
  as = "article",
  children,
  className,
  ...rest
}: SurfaceContainerProps) {
  const Component = as as ElementType;

  return (
    <Component
      className={joinClassNames(
        "surface-detail-card",
        "workspace-card",
        "section-stack",
        className,
      )}
      {...rest}
    >
      {children}
    </Component>
  );
}

export function SurfaceDrawer({
  as = "aside",
  children,
  className,
  ...rest
}: SurfaceContainerProps) {
  const Component = as as ElementType;

  return (
    <Component
      className={joinClassNames(
        "surface-drawer",
        "surface-card",
        "section-stack",
        className,
      )}
      {...rest}
    >
      {children}
    </Component>
  );
}

export function SurfaceTableFrame({
  children,
  className,
  ...rest
}: SurfaceTableFrameProps) {
  return (
    <div
      className={joinClassNames("surface-table-frame", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function SurfaceTable({
  children,
  className,
  ...rest
}: SurfaceTableProps) {
  return (
    <table className={joinClassNames("surface-table", className)} {...rest}>
      {children}
    </table>
  );
}

export function SurfaceMetricCard({
  as = "article",
  badge,
  className,
  detail,
  eyebrow,
  title,
  value,
  ...rest
}: SurfaceMetricCardProps) {
  const Component = as as ElementType;

  return (
    <Component
      className={joinClassNames(
        "surface-metric-card",
        "surface-card",
        "section-stack",
        className,
      )}
      {...rest}
    >
      {badge}
      {eyebrow ? <p className="surface-metric-eyebrow">{eyebrow}</p> : null}
      <strong className="surface-metric-value">{value}</strong>
      {title ? <p className="surface-metric-title">{title}</p> : null}
      {detail ? <p className="surface-metric-detail">{detail}</p> : null}
    </Component>
  );
}

export function SurfaceBarRow({
  className,
  detail,
  label,
  progress,
  value,
  ...rest
}: SurfaceBarRowProps) {
  const normalizedProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className={joinClassNames("surface-bar-row", className)} {...rest}>
      <div className="surface-bar-header">
        <strong className="surface-bar-label">{label}</strong>
        <span className="surface-bar-value">{value}</span>
      </div>
      {detail ? <p className="surface-bar-detail">{detail}</p> : null}
      <div aria-hidden="true" className="surface-bar-meter">
        <span
          className="surface-bar-fill"
          style={{ width: `${normalizedProgress}%` }}
        />
      </div>
    </div>
  );
}

export function SurfaceColumnChart({
  className,
  items,
  ...rest
}: SurfaceColumnChartProps) {
  return (
    <div className={joinClassNames("surface-column-chart", className)} {...rest}>
      {items.map((item, index) => {
        const normalizedHeight = Math.max(8, Math.min(100, item.height));

        return (
          <div className="surface-column-item" key={item.id || `column-${index}`}>
            <span className="surface-column-value">{item.value}</span>
            <div aria-hidden="true" className="surface-column-meter">
              <span
                className="surface-column-fill"
                data-tone={item.tone || "accent"}
                style={{ height: `${normalizedHeight}%` }}
              />
            </div>
            <strong className="surface-column-label">{item.label}</strong>
            {item.detail ? (
              <span className="surface-column-detail">{item.detail}</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function SectionHeading({
  actions,
  className,
  description,
  title,
}: SectionHeadingProps) {
  return (
    <div
      className={joinClassNames(
        actions ? "section-heading section-heading-row" : "section-heading",
        className,
      )}
    >
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {actions}
    </div>
  );
}

export function SurfaceTimelineItem({
  as = "article",
  badge,
  children,
  className,
  description,
  eyebrow,
  markerState = "complete",
  title,
  ...rest
}: SurfaceTimelineItemProps) {
  const Component = as as ElementType;

  return (
    <Component
      className={joinClassNames(
        "surface-timeline-item",
        "timeline-card",
        className,
      )}
      {...rest}
    >
      <span className="timeline-marker" data-state={markerState} />
      <div>
        <div className="timeline-header-row">
          <div>
            {eyebrow ? <span className="queue-card-label">{eyebrow}</span> : null}
            <h3>{title}</h3>
          </div>
          {badge}
        </div>
        {description ? <p className="timeline-detail">{description}</p> : null}
        {children}
      </div>
    </Component>
  );
}

export function SurfaceDialog({
  actions,
  as = "section",
  badge,
  children,
  className,
  description,
  title,
  ...rest
}: SurfaceDialogProps) {
  const Component = as as ElementType;
  const headingId = useId();
  const descriptionId = useId();

  return (
    <Component
      aria-describedby={description ? descriptionId : undefined}
      aria-labelledby={headingId}
      className={joinClassNames(
        "surface-dialog",
        "surface-card",
        "section-stack",
        className,
      )}
      role="dialog"
      {...rest}
    >
      <div className="surface-dialog-header">
        <div className="surface-dialog-copy">
          {badge}
          <h3 id={headingId}>{title}</h3>
          {description ? (
            <p className="surface-panel-copy" id={descriptionId}>
              {description}
            </p>
          ) : null}
        </div>
        {actions ? <div className="surface-dialog-actions">{actions}</div> : null}
      </div>
      {children ? <div className="surface-dialog-body">{children}</div> : null}
    </Component>
  );
}

export function StatusBadge({
  children,
  className,
  tone = "neutral",
  ...rest
}: StatusBadgeProps) {
  return (
    <span
      className={joinClassNames("status-badge", className)}
      data-tone={tone}
      {...rest}
    >
      {children}
    </span>
  );
}