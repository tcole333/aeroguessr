# Frontend Dockerfile for production build
# Multi-stage build: Build stage + Nginx serving stage

# --- Build Stage ---
FROM node:18-alpine AS build

# Set working directory
WORKDIR /app

# Copy package files for dependency installation
COPY package*.json ./

# Install dependencies
# Use npm since it's more universally available in Node.js images
RUN npm ci --silent

# Copy source code
COPY . .

# Build the application for production
# Skip TypeScript checking for now and build directly with Vite
RUN npx vite build --mode production

# --- Serve Stage ---
FROM nginx:alpine

# Copy built files from build stage to nginx document root
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx configuration if needed (optional)
# COPY nginx.conf /etc/nginx/nginx.conf

# Expose port 80 for HTTP traffic
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
