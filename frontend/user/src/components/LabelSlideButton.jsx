"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useAnimate, useReducedMotion } from "motion/react";

const borderWidthOf = (b) =>
  Math.max(
    0,
    ...[
      b?.borderWidth,
      b?.borderTopWidth,
      b?.borderRightWidth,
      b?.borderBottomWidth,
      b?.borderLeftWidth,
    ].map((v) => parseFloat(String(v ?? "")) || 0)
  );

const borderColorOf = (b) => b?.borderColor ?? "transparent";

const borderBoxOf = (b) => {
  const { borderColor, ...rest } = b ?? {};
  return rest;
};

const DEFAULT_TRANSITION = {
  type: "tween",
  duration: 0.35,
  ease: [0.16, 1, 0.3, 1],
};

const ICON_TRANSITION = { duration: 0.25, ease: "easeInOut" };

const COLOR_DEFAULTS = {
  fill: "var(--color-primary, #9CAF88)",
  textColor: "#FFFFFF",
  hoverFill: "var(--color-primary-hover, #889b74)",
  hoverTextColor: "#FFFFFF",
};

const ICON_DEFAULTS = {
  background: "rgba(255, 255, 255, 0.2)",
  color: "#FFFFFF",
  hoverBackground: "#FFFFFF",
  hoverColor: "var(--color-primary, #9CAF88)",
  restSymbol: "↗",
  hoverSymbol: "↗",
  size: 16,
  padding: 8,
  angle: 315,
};

const radiusFromPercent = (w, h, pct) =>
  (Math.min(w, h) / 2) * (Math.max(0, Math.min(100, pct)) / 100);

const useIsoLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

const normalizeAngle = (deg) => {
  const parsed =
    typeof deg === "number" ? deg : parseFloat(String(deg ?? ""));
  if (!Number.isFinite(parsed)) return ICON_DEFAULTS.angle;
  return ((parsed % 360) + 360) % 360;
};

const srcOf = (img) =>
  typeof img === "string" ? img : img && img.src ? img.src : "";

const ARROW_ANGLES = {
  "↗": 315,
  "→": 0,
  "↘": 45,
  "↓": 90,
  "↙": 135,
  "←": 180,
  "↖": 225,
  "↑": 270,
};

const arrowAngleOf = (symbol) =>
  ARROW_ANGLES[typeof symbol === "string" ? symbol.trim() : ""];

export function LabelSlideButton(props) {
  const {
    label = "Add to Cart",
    showText = true,
    textSide = "top",
    font = {
      fontSize: "0.9rem",
      fontWeight: 700,
      letterSpacing: "0.02em",
    },
    padding = "10px 20px",
    rounded = 100,
    colors,
    border = { borderColor: "transparent", borderStyle: "solid", borderWidth: 0 },
    hoverBorderColor,
    addIcon = true,
    icon = {
      side: "right",
      size: 16,
      type: "symbol",
      angle: 315,
      color: "#FFFFFF",
      padding: 8,
      rounded: 100,
      restImage: "",
      background: "rgba(255, 255, 255, 0.2)",
      hoverColor: "var(--accent-indigo, #4f46e5)",
      hoverImage: "",
      restSymbol: "↗",
      hoverSymbol: "↗",
      hoverBackground: "#FFFFFF",
    },
    gap = 12,
    link,
    transition = { ease: [0.16, 1, 0.3, 1], type: "tween", duration: 0.35 },
    newTab = true,
    style,
    className = "",
    onClick,
    disabled = false,
    ...restProps
  } = props;

  const {
    type: iconType = "symbol",
    restSymbol = ICON_DEFAULTS.restSymbol,
    hoverSymbol = ICON_DEFAULTS.hoverSymbol,
    restImage,
    hoverImage,
    color: iconColor = ICON_DEFAULTS.color,
    hoverColor: hoverIconColor = ICON_DEFAULTS.hoverColor,
    size: iconSizeProp = ICON_DEFAULTS.size,
    padding: iconPaddingProp = ICON_DEFAULTS.padding,
    rounded: iconRounded = 100,
    background: iconBg = ICON_DEFAULTS.background,
    hoverBackground: hoverIconBg = ICON_DEFAULTS.hoverBackground,
    angle: moveAngleProp = ICON_DEFAULTS.angle,
    side: iconSideProp = "right",
    position: iconPositionLegacy,
  } = icon;

  const iconPosition = iconSideProp ?? iconPositionLegacy ?? "right";

  const [scope, animate] = useAnimate();
  const labelUpRef = useRef(null);
  const labelDownRef = useRef(null);
  const badgeRef = useRef(null);

  const iconOutRef = useRef(null);
  const iconInRef = useRef(null);
  const hovered = useRef(false);
  const reducedMotion = useReducedMotion();

  useIsoLayoutEffect(() => {
    const root = scope.current;
    if (!root) return;
    const applyRadius = () => {
      const w = root.offsetWidth;
      const h = root.offsetHeight;
      if (!w || !h) return;
      root.style.borderRadius = `${radiusFromPercent(w, h, rounded)}px`;
    };
    applyRadius();
    const ro = new ResizeObserver(applyRadius);
    ro.observe(root);
    return () => ro.disconnect();
  }, [scope, rounded, padding, showText]);

  const fontStyles = { ...(font ?? {}) };
  const glyphSize = Math.max(1, Math.round(iconSizeProp));
  const iconRadius = radiusFromPercent(glyphSize, glyphSize, iconRounded);
  const iconPadding = Math.max(0, Math.round(iconPaddingProp));
  const badgeSize = glyphSize + iconPadding * 2;
  const badgeRadius = `${Math.max(0, Math.min(100, Math.round(iconRounded))) / 2}%`;

  const moveAngle = normalizeAngle(moveAngleProp);
  const travel = (glyphSize + 2) * 1.5;
  const travelX = Math.cos((moveAngle * Math.PI) / 180) * travel;
  const travelY = Math.sin((moveAngle * Math.PI) / 180) * travel;

  const labelExit = textSide === "bottom" ? "100%" : "-100%";
  const labelEnter = textSide === "bottom" ? "-100%" : "100%";

  const { fill, textColor, hoverFill, hoverTextColor } = {
    ...COLOR_DEFAULTS,
    ...(colors ?? {}),
  };

  const resolvedHoverBorderColor = hoverBorderColor ?? borderColorOf(border);

  const opts = useCallback(
    () => (reducedMotion ? { duration: 0 } : transition),
    [reducedMotion, transition]
  );

  const apply = useCallback(
    (toHover, instant) => {
      const t = instant ? { duration: 0 } : opts();
      const it = instant || reducedMotion ? { duration: 0 } : ICON_TRANSITION;

      const rootColors = {
        backgroundColor: toHover ? hoverFill : fill,
        color: toHover ? hoverTextColor : textColor,
        borderColor: toHover ? resolvedHoverBorderColor : borderColorOf(border),
      };
      const badgeColors = {
        backgroundColor: toHover ? hoverIconBg : iconBg,
        color: toHover ? hoverIconColor : iconColor,
      };

      if (instant) {
        Object.assign(scope.current?.style ?? {}, rootColors);
        Object.assign(badgeRef.current?.style ?? {}, badgeColors);
      }

      if (scope.current && !instant)
        animate(scope.current, rootColors, t);
      if (labelUpRef.current)
        animate(labelUpRef.current, { y: toHover ? labelExit : "0%" }, t);
      if (labelDownRef.current)
        animate(labelDownRef.current, { y: toHover ? "0%" : labelEnter }, t);
      if (badgeRef.current && !instant)
        animate(badgeRef.current, badgeColors, t);
      if (iconOutRef.current)
        animate(
          iconOutRef.current,
          {
            x: toHover ? travelX : 0,
            y: toHover ? travelY : 0,
            opacity: toHover ? 0 : 1,
          },
          it
        );
      if (iconInRef.current)
        animate(
          iconInRef.current,
          {
            x: toHover ? 0 : -travelX,
            y: toHover ? 0 : -travelY,
            opacity: toHover ? 1 : 0,
          },
          it
        );
    },
    [
      animate,
      scope,
      opts,
      reducedMotion,
      fill,
      hoverFill,
      textColor,
      hoverTextColor,
      border,
      resolvedHoverBorderColor,
      iconBg,
      hoverIconBg,
      iconColor,
      hoverIconColor,
      travelX,
      travelY,
      labelExit,
      labelEnter,
    ]
  );

  useIsoLayoutEffect(() => {
    if (hovered.current) return;
    apply(false, true);
  }, [apply, showText, addIcon]);

  const onEnter = () => {
    if (disabled) return;
    hovered.current = true;
    apply(true, false);
  };

  const onLeave = () => {
    if (disabled) return;
    hovered.current = false;
    apply(false, false);

    if (scope.current)
      animate(scope.current, { scale: 1 }, opts());
  };

  const onFocus = (e) => {
    if (e.currentTarget.matches(":focus-visible")) onEnter();
  };

  const onBlur = () => {
    if (hovered.current) onLeave();
  };

  const isLink = typeof link === "string" && link.length > 0;
  const Tag = isLink ? "a" : "button";
  const tagProps = {
    "aria-label": showText ? undefined : label || undefined,
    ...(isLink
      ? {
          href: link,
          target: newTab ? "_blank" : undefined,
          rel: newTab ? "noopener noreferrer" : undefined,
        }
      : { type: "button", disabled }),
  };

  const renderIcon = (symbol, image) => {
    const src = srcOf(image);
    if (iconType === "image" && src)
      return (
        <img
          src={src}
          alt=""
          aria-hidden
          draggable={false}
          style={{
            width: glyphSize,
            height: glyphSize,
            objectFit: iconRadius > 0 ? "cover" : "contain",
            borderRadius: Math.min(iconRadius, glyphSize / 2),
            display: "block",
            pointerEvents: "none",
          }}
        />
      );

    const arrowAngle = iconType === "symbol" ? arrowAngleOf(symbol) : undefined;
    if (arrowAngle !== undefined) {
      const rotation = arrowAngle - 315;
      return (
        <svg
          width={glyphSize}
          height={glyphSize}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            display: "block",
            transform: `rotate(${rotation}deg)`,
            pointerEvents: "none",
          }}
        >
          <path d="M7 17L17 7" />
          <path d="M7 7h10v10" />
        </svg>
      );
    }

    return (
      <span
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: glyphSize,
          lineHeight: 1,
          color: "currentColor",
          fontFamily: "inherit",
          whiteSpace: "nowrap",
        }}
      >
        {symbol}
      </span>
    );
  };

  return (
    <Tag
      {...tagProps}
      {...restProps}
      ref={scope}
      className={className}
      onClick={onClick}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onPointerCancel={onLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onPointerDown={() =>
        !disabled &&
        scope.current &&
        animate(scope.current, { scale: 0.97 }, opts())
      }
      onPointerUp={() =>
        !disabled &&
        scope.current &&
        animate(scope.current, { scale: 1 }, opts())
      }
      style={{
        display: "inline-flex",
        flexDirection: iconPosition === "left" ? "row-reverse" : "row",
        alignItems: "center",
        justifyContent: "center",
        gap: showText && addIcon ? `${gap}px` : 0,
        padding,
        ...borderBoxOf(border),
        textDecoration: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        overflow: "hidden",
        position: "relative",
        userSelect: "none",
        boxSizing: "border-box",
        willChange: "transform",
        ...fontStyles,
        minWidth: "min-content",
        minHeight: "min-content",
        ...style,
      }}
    >
      {showText && (
        <span
          style={{
            position: "relative",
            display: "inline-block",
            overflow: "hidden",
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ visibility: "hidden" }}>{label}</span>
          <span
            ref={labelUpRef}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {label}
          </span>
          <span
            ref={labelDownRef}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transform: `translateY(${labelEnter})`,
            }}
          >
            {label}
          </span>
        </span>
      )}

      {addIcon && (
        <span
          ref={badgeRef}
          style={{
            position: "relative",
            flexShrink: 0,
            width: badgeSize,
            height: badgeSize,
            borderRadius: badgeRadius,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            ref={iconOutRef}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {renderIcon(restSymbol, restImage)}
          </span>
          <span
            ref={iconInRef}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: 0,
            }}
          >
            {renderIcon(hoverSymbol, hoverImage)}
          </span>
        </span>
      )}
    </Tag>
  );
}

const __originkitPresetProps = {
  icon: {
    side: "right",
    size: 16,
    type: "symbol",
    angle: 315,
    color: "#FFFFFF",
    padding: 8,
    rounded: 100,
    restImage: "",
    background: "rgba(255, 255, 255, 0.2)",
    hoverColor: "var(--accent-indigo, #4f46e5)",
    hoverImage: "",
    restSymbol: "↗",
    hoverSymbol: "↗",
    hoverBackground: "#FFFFFF",
  },
};

export default function LabelSlideButtonPreset(props) {
  return (
    <LabelSlideButton
      {...__originkitPresetProps}
      {...props}
    />
  );
}
