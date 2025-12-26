import { cookies } from 'next/headers'
import { verifyToken } from './auth'
import { prisma } from './prisma'

export async function getCurrentUser() {
  try {
    const cookieStore = await cookies()
    const token = cookieStore.get('token')?.value

    if (!token) {
      return null
    }

    const decoded = verifyToken(token)
    if (!decoded) {
      return null
    }

    const user = await prisma.user.findUnique({
      where: { id: decoded.userId },
      select: { id: true, email: true, name: true },
    })

    return user
  } catch {
    return null
  }
}


