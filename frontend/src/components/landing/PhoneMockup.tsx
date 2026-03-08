/**
 * Phone Mockup Component
 *
 * Claude-style dark phone mockup with animated workflow demo.
 */

import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/utils/cn'

interface PhoneMockupProps {
  className?: string
}

export function PhoneMockup({ className }: PhoneMockupProps) {
  const { t } = useTranslation('landing')
  const [animationStep, setAnimationStep] = useState(0)
  const [isVisible, setIsVisible] = useState(false)
  const [hasCompleted, setHasCompleted] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // Intersection observer to start animation when visible
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasCompleted) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.3 }
    )

    if (containerRef.current) {
      observer.observe(containerRef.current)
    }

    return () => observer.disconnect()
  }, [hasCompleted])

  // Animation sequence - plays once, then keeps final state
  useEffect(() => {
    if (!isVisible || hasCompleted) return

    const delays = [300, 1000, 1800, 3200, 3500]
    const timers: ReturnType<typeof setTimeout>[] = []

    delays.forEach((delay, index) => {
      const timer = setTimeout(() => {
        setAnimationStep(index + 1)
        // Mark as completed when reaching final step
        if (index === delays.length - 1) {
          setHasCompleted(true)
        }
      }, delay)
      timers.push(timer)
    })

    return () => timers.forEach(clearTimeout)
  }, [isVisible, hasCompleted])

  // Auto scroll to bottom when content changes
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTo({
        top: contentRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [animationStep])

  // Get workflow steps from translations
  const workflowSteps = [
    { icon: 'CRM', name: t('phoneMockup.steps.crm') },
    { icon: 'Drive', name: t('phoneMockup.steps.drive') },
    { icon: 'Mail', name: t('phoneMockup.steps.mail') },
    { icon: 'Sheet', name: t('phoneMockup.steps.sheet') },
    { icon: 'Chat', name: t('phoneMockup.steps.chat') },
  ]

  // Get status items from translations
  const statusItems = t('phoneMockup.statusItems', { returnObjects: true }) as string[]

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative w-[340px] h-[700px] bg-gray-900 rounded-[50px] p-3.5 shadow-2xl',
        className
      )}
    >
      {/* Phone screen */}
      <div className="w-full h-full bg-[#1f1f1f] rounded-[38px] overflow-hidden flex flex-col">
        {/* Phone content */}
        <div
          ref={contentRef}
          className="flex-1 overflow-y-auto overflow-x-hidden pt-4 scrollbar-hide"
        >
          {/* Step 1: User message */}
          {animationStep >= 1 && (
            <div className="px-5 mb-4 animate-fade-in">
              <div className="bg-[#2f2f2f] text-white px-4 py-3 rounded-2xl rounded-br-md ml-auto max-w-[85%] font-serif text-sm">
                {t('phoneMockup.userMessage')}
              </div>
            </div>
          )}

          {/* Step 2: Thinking section */}
          {animationStep >= 2 && (
            <div className="px-5 mb-4 animate-fade-in">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-5 h-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 6v6l4 2"/>
                </svg>
                <span className="text-sm font-medium text-gray-200">{t('phoneMockup.thinkingTitle')}</span>
              </div>
              <p className="text-sm text-gray-400 italic font-serif">
                {t('phoneMockup.thinkingText')}
              </p>
            </div>
          )}

          {/* Step 3: Tool card with workflow */}
          {animationStep >= 3 && (
            <div className="mx-5 mb-4 bg-[#2a2a2a] border border-gray-700 rounded-xl p-4 animate-fade-in">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-6 h-6 bg-gray-700 rounded-md flex items-center justify-center">
                  <svg className="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                    <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
                  </svg>
                </div>
                <span className="text-sm font-semibold text-white font-mono">{t('phoneMockup.workflowName')}</span>
              </div>

              <div className="text-xs text-gray-400 mb-3">
                <span className="opacity-70">{t('phoneMockup.workflowInfo')}</span>
              </div>

              {/* Service steps */}
              <div className="flex flex-col gap-2 pl-3 border-l-2 border-gray-700 ml-1">
                {workflowSteps.map((step, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-gray-400">
                    <div className="w-3 h-3 bg-orange rounded-full" />
                    <span>{step.name}</span>
                  </div>
                ))}
              </div>

              {/* Loading or completed state */}
              <div className="flex justify-center py-3 mt-2">
                {animationStep < 4 ? (
                  <div className="w-8 h-8 border-3 border-gray-600 border-t-orange rounded-full animate-spin" />
                ) : (
                  <div className="flex items-center gap-2 text-success text-sm">
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    <span>{t('phoneMockup.workflowCompleted')}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 5: Result */}
          {animationStep >= 5 && (
            <div className="px-5 mb-4 animate-fade-in">
              <div className="bg-[#2a2a2a] text-gray-200 p-4 rounded-2xl rounded-bl-md font-serif text-sm">
                <div className="font-semibold mb-3 text-white flex items-center gap-2">
                  <span className="text-lg">✓</span>
                  <span>{t('phoneMockup.resultTitle')}</span>
                </div>

                <p className="mb-3" dangerouslySetInnerHTML={{ __html: t('phoneMockup.resultIntro') }} />

                {/* Result cards */}
                <div className="space-y-2">
                  <ResultCard
                    icon="CRM"
                    title={t('phoneMockup.hubspotTitle')}
                    subtitle={t('phoneMockup.hubspotSubtitle')}
                    details={t('phoneMockup.hubspotDetails')}
                  />
                  <ResultCard
                    icon="Drive"
                    title={t('phoneMockup.driveTitle')}
                    subtitle={t('phoneMockup.driveSubtitle')}
                    details={t('phoneMockup.driveDetails')}
                  />
                </div>

                {/* Quick status items */}
                <div className="grid gap-2 mt-3 text-xs">
                  {statusItems.map((item, i) => (
                    <div key={i} className="bg-[#1f1f1f] border border-gray-700 rounded-md px-3 py-2 flex items-center gap-2">
                      <svg className="w-3.5 h-3.5 text-success" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                      </svg>
                      <span className="text-gray-200">{item}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-4 pt-3 border-t border-gray-700">
                  {t('phoneMockup.conclusion')}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="px-5 py-4 bg-[#2a2a2a] border-t border-gray-700 flex items-center gap-3">
          <span className="flex-1 text-sm text-gray-500 italic font-serif">{t('phoneMockup.replyPlaceholder')}</span>
          <svg className="w-7 h-7 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="9"/>
            <path d="M12 8v8m4-4H8"/>
          </svg>
        </div>
      </div>
    </div>
  )
}

function ResultCard({ icon, title, subtitle, details }: {
  icon: string
  title: string
  subtitle: string
  details: string
}) {
  return (
    <div className="bg-[#1f1f1f] border border-gray-700 rounded-lg p-3 text-xs">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-4 h-4 bg-orange rounded-full" />
        <span className="text-white font-semibold">{title}</span>
        <span className="bg-success px-1.5 py-0.5 rounded text-[10px] text-white font-semibold">✓</span>
      </div>
      <div className="text-gray-200 font-medium mb-0.5">{subtitle}</div>
      <div className="text-gray-400 leading-snug">{details}</div>
    </div>
  )
}
