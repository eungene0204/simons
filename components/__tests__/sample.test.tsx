import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// A simple component for testing
const SampleComponent = () => <div>Hello, Vitest!</div>;

// A simple function for testing
const add = (a: number, b: number) => a + b;

describe('Sample Test', () => {
  it('should add two numbers correctly', () => {
    expect(add(1, 2)).toBe(3);
  });

  it('should render the sample component correctly', () => {
    render(<SampleComponent />);
    expect(screen.getByText('Hello, Vitest!')).toBeInTheDocument();
  });
});
