import Link from 'next/link'
import { ReactNode } from 'react'
import { t } from "@/lib/i18n";

type AuthCardProps = {
  title: string
  subtitle?: ReactNode
  children: ReactNode
}

export default function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <div className="w-full max-w-md">
      <div className="mb-8 flex items-center gap-3">
        <div className="h-10 w-10 rounded bg-gray-900 dark:bg-gray-100" />
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{t("널스탁")}</p>
          <h1 className="text-xl font-semibold">{title}</h1>
        </div>
      </div>
      {subtitle}
      <div className="mt-6">
        {children}
      </div>
    </div>
  )
}



