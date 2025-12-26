import { InputHTMLAttributes, forwardRef } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label?: string
}

const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { label, id, className = '', ...props },
  ref
) {
  return (
    <div>
      {label ? (
        <label htmlFor={id} className="block text-sm font-medium mb-1">{label}</label>
      ) : null}
      <input
        ref={ref}
        id={id}
        className={`w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-100 ${className}`}
        {...props}
      />
    </div>
  )
})

export default Input



