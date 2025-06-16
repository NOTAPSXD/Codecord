'use client';

import { SignedIn, SignedOut, SignInButton, UserButton } from '@clerk/nextjs';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-blue-100 via-white to-blue-300 px-4">
      <header className="w-full max-w-6xl flex justify-between items-center py-6">
        <div className="flex items-center gap-2">
          <img src="https://png.pngtree.com/png-vector/20220607/ourmid/pngtree-blue-code-icon-on-white-background-png-image_4855266.png" alt="Logo" className="w-10 h-10" />
          <span className="text-2xl font-bold text-blue-700">Code X Tutorial</span>
        </div>
        <nav>
          <SignedOut>
            <SignInButton>
              <button className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold shadow hover:bg-blue-700 transition">
                Login
              </button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
        </nav>
      </header>
      <section className="flex-1 flex flex-col items-center justify-center text-center">
        <h1 className="text-5xl md:text-6xl font-extrabold text-blue-800 mb-6">
          Welcome to <span className="text-blue-600">Code X Tutorial</span>
        </h1>
        <p className="text-lg md:text-2xl text-gray-600 mb-10 max-w-2xl">
          The Best Place For Learning Modern Web Development. Join our community of developers and start your coding journey today!
        </p>
        <SignedOut>
          <SignInButton>
            <button className="px-8 py-3 bg-blue-600 text-white rounded-xl font-bold text-lg shadow-lg hover:bg-blue-700 transition">
              Get Started
            </button>
          </SignInButton>
        </SignedOut>
      </section>
      <footer className="w-full text-center py-4 text-gray-400 text-sm">
        &copy; {new Date().getFullYear()} Code X Tutorial. All rights reserved.
      </footer>
    </main>
  );
}
