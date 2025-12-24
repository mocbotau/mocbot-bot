package main

import (
	"context"

	"dagger/mocbot-bot/internal/dagger"
)

const (
	repoName      = "mocbot-bot"
	pythonVersion = "3.10"
)

type MocbotBot struct {
	// Source code directory
	Source *dagger.Directory
	// +private
	InfisicalClientSecret *dagger.Secret
}

func New(
	// Source code directory
	// +defaultPath="."
	source *dagger.Directory,
	infisicalClientSecret *dagger.Secret,
) *MocbotBot {
	return &MocbotBot{
		Source:                source,
		InfisicalClientSecret: infisicalClientSecret,
	}
}

// CI runs the complete CI pipeline (lint checks)
func (m *MocbotBot) CI(ctx context.Context) error {
	srcDir := m.Source.Directory("lib").WithFile(".", m.Source.File(".flake8"))

	_, err := dag.PythonCi(srcDir, dagger.PythonCiOpts{PythonVersion: pythonVersion}).Lint(ctx)
	if err != nil {
		return err
	}

	return nil
}

// BuildAndPush builds and pushes the Docker image to the container registry
func (m *MocbotBot) BuildAndPush(
	ctx context.Context,
	// Environment to build image for
	// +default="staging"
	env string,
) (string, error) {
	docker := dag.Docker(m.Source, m.InfisicalClientSecret, repoName, dagger.DockerOpts{
		Environment: env,
	})

	return docker.Build().Publish(ctx)
}
