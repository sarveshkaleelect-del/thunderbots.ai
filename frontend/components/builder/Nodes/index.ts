import {
  StartNode, TextCardNode, MultipleChoiceNode, AIAgentNode, TransitionNode, EndNode,
  ConditionNode, LinkNode, RatingNode, LocationNode, VideoNode,
} from './NodeComponents'

export const nodeTypes = {
  start:           StartNode,
  text_card:       TextCardNode,
  multiple_choice: MultipleChoiceNode,
  ai_agent:        AIAgentNode,
  transition:      TransitionNode,
  end:             EndNode,
  condition:       ConditionNode,
  link:            LinkNode,
  rating:          RatingNode,
  location:        LocationNode,
  video:           VideoNode,
}

export {
  StartNode, TextCardNode, MultipleChoiceNode, AIAgentNode, TransitionNode, EndNode,
  ConditionNode, LinkNode, RatingNode, LocationNode, VideoNode,
}
