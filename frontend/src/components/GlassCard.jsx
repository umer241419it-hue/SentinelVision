import './GlassCard.css';

/**
 * HUDPanel — angular clipped panel with HUD corner brackets.
 * Exported under the legacy name `GlassCard` so existing page imports
 * keep working; also exported as `HUDPanel`.
 *
 * props: corners (bool, default true), glow ('cyan'|'violet'), pad, onClick
 */
function HUDPanel({ children, className = '', glow, pad = true, corners = true, onClick }) {
  return (
    <div
      className={[
        'hud-panel',
        corners ? 'hud-corners' : '',
        pad ? 'padded' : '',
        glow ? `glow-${glow}` : '',
        onClick ? 'clickable' : '',
        className
      ].join(' ')}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

export default HUDPanel;
export { HUDPanel };
