"use client"

import { useEffect, useState } from "react"
import { getScoreColor, getScoreLabel } from "@/lib/utils"

interface ScoreGaugeProps {
  score: number | null | undefined
  size?: number
  strokeWidth?: number
  className?: string
}

export function ScoreGauge({
  score,
  size = 180,
  strokeWidth = 14,
  className,
}: ScoreGaugeProps) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const normalizedScore = score != null ? Math.min(100, Math.max(0, score)) : 0
  const strokeDashoffset = circumference - (animatedScore / 100) * circumference
  const color = getScoreColor(score)
  const label = getScoreLabel(score)

  useEffect(() => {
    if (score == null) {
      setAnimatedScore(0)
      return
    }
    const timer = setTimeout(() => {
      setAnimatedScore(normalizedScore)
    }, 100)
    return () => clearTimeout(timer)
  }, [score, normalizedScore])

  return (
    <div className={className} role="img" aria-label={`Score: ${score != null ? Math.round(score) : "sem dados"}`}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="block"
      >
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted/40"
        />
        {/* Animated progress arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dashoffset 1s ease-out" }}
        />
        {/* Score number */}
        <text
          x="50%"
          y="46%"
          dominantBaseline="middle"
          textAnchor="middle"
          className="fill-foreground text-4xl font-bold"
          style={{ fontSize: size * 0.22 }}
        >
          {score != null ? Math.round(score) : "—"}
        </text>
        {/* Label */}
        <text
          x="50%"
          y="62%"
          dominantBaseline="middle"
          textAnchor="middle"
          className="fill-muted-foreground"
          style={{ fontSize: size * 0.09 }}
        >
          {label}
        </text>
      </svg>
    </div>
  )
}
