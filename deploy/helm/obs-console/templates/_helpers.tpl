{{- define "obs.backendImage" -}}
{{ .Values.backendImage.repository }}{{ if .Values.backendImage.digest }}@{{ .Values.backendImage.digest }}{{ else }}:{{ .Values.backendImage.tag }}{{ end }}
{{- end -}}
{{- define "obs.webImage" -}}
{{ .Values.webImage.repository }}{{ if .Values.webImage.digest }}@{{ .Values.webImage.digest }}{{ else }}:{{ .Values.webImage.tag }}{{ end }}
{{- end -}}
